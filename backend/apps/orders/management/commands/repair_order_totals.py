"""Realinha taxa de servico e total de pedidos que ficaram com valor errado.

Serve ao residuo de um problema que ja foi corrigido na origem: enquanto a taxa
de servico ficava congelada no subtotal do fechamento, todo item que chegava
depois (a fila offline do PDV entrega na ordem dela, e um item recusado por
preco sobe depois de corrigido) aumentava o subtotal sem aumentar a taxa. Esses
pedidos ficaram no banco com `total != subtotal + taxa`, e um a um nao ha como
consertar.

O comando NAO toca pedido pago, cancelado ou estornado: livro fechado se
corrige por estorno, nao por UPDATE. Sem `--apply` apenas relata.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.orders.models import Order
from apps.orders.services import TWO_PLACES, recalculate_order

REPAIRABLE_STATUSES = (Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT)


class Command(BaseCommand):
    help = "Recalcula taxa de servico e total de pedidos abertos ou aguardando pagamento."

    def add_arguments(self, parser):
        parser.add_argument("--order", default=None, help="Corrige um unico pedido, pelo id.")
        parser.add_argument("--restaurant", default=None, help="Limita a um restaurante, pelo id.")
        parser.add_argument("--branch", default=None, help="Limita a uma filial, pelo id.")
        parser.add_argument(
            "--adopt-restaurant-percent",
            action="store_true",
            help=(
                "Para pedidos fechados ANTES de a aliquota passar a ser gravada: adota o "
                "percentual padrao do restaurante. Uma taxa que o gerente digitou a mao "
                "tambem seria reescrita, por isso a decisao e explicita."
            ),
        )
        parser.add_argument("--apply", action="store_true", help="Grava. Sem isto, so relata.")

    def handle(self, *args, **options):
        # `all_objects`: um comando roda fora de contexto de tenant, e o manager
        # padrao devolveria vazio para todas as contas.
        orders = Order.all_objects.filter(status__in=REPAIRABLE_STATUSES).select_related(
            "restaurant", "account"
        )
        if options["order"]:
            orders = orders.filter(pk=options["order"])
        if options["restaurant"]:
            orders = orders.filter(restaurant_id=options["restaurant"])
        if options["branch"]:
            orders = orders.filter(branch_id=options["branch"])
        if options["order"] and not orders.exists():
            raise CommandError(f"Pedido {options['order']} nao existe, ou ja esta pago/cancelado.")

        divergent = 0
        repaired = 0
        for order in orders.order_by("opened_at").iterator():
            before = (order.subtotal, order.service_fee, order.total)
            after = self._projection(order, adopt=options["adopt_restaurant_percent"])
            if after == before:
                continue
            divergent += 1
            self.stdout.write(
                f"#{order.sequence} {order.id} "
                f"subtotal {before[0]}->{after[0]} "
                f"taxa {before[1]}->{after[1]} "
                f"total {before[2]}->{after[2]}"
            )
            if not options["apply"]:
                continue
            self._repair(order, adopt=options["adopt_restaurant_percent"])
            repaired += 1

        verb = "corrigidos" if options["apply"] else "divergentes (nada gravado)"
        self.stdout.write(self.style.SUCCESS(f"{divergent} pedidos {verb}; {repaired} gravados."))

    def _projection(self, order, *, adopt):
        """O que o recalculo produziria, sem gravar nada."""
        excluded = {"cancelled", "comped"}
        subtotal = sum(
            (item.total_price for item in order.items.exclude(status__in=excluded)),
            Decimal("0.00"),
        )
        percent = self._percent_for(order, adopt=adopt)
        if not order.service_fee_enabled:
            fee = Decimal("0.00")
        elif percent is None:
            fee = order.service_fee
        else:
            fee = ((subtotal * percent) / Decimal("100")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        total = max(subtotal + fee + order.delivery_fee - order.discount, Decimal("0.00"))
        return (subtotal, fee, total)

    def _percent_for(self, order, *, adopt):
        if order.service_fee_percent is not None:
            return order.service_fee_percent
        if adopt and order.status == Order.STATUS_AWAITING_PAYMENT:
            return order.restaurant.default_service_fee_percent or Decimal("0.00")
        return None

    def _repair(self, order, *, adopt):
        with tenant_context(order.account), transaction.atomic():
            locked = Order.all_objects.select_for_update().get(pk=order.pk)
            percent = self._percent_for(locked, adopt=adopt)
            if percent is not None and locked.service_fee_percent != percent:
                locked.service_fee_percent = percent
                locked.save(update_fields=["service_fee_percent"])
            before_total = locked.total
            fixed = recalculate_order(locked)
            record_audit(
                action=AuditLog.ACTION_UPDATED,
                instance=fixed,
                actor=None,
                reason="repair_order_totals",
                metadata={
                    "event": "repair_order_totals",
                    "total_before": str(before_total),
                    "total_after": str(fixed.total),
                    "service_fee_percent": str(fixed.service_fee_percent),
                },
            )
