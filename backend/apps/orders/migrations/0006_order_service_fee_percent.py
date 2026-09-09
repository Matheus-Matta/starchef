"""Guarda a aliquota da taxa de servico e conserta os totais que ficaram errados.

Enquanto a taxa de servico era so um valor em reais, ela ficava congelada no
subtotal do fechamento: todo item que chegava depois (a fila offline do PDV
entrega na ordem dela, e um item recusado por preco sobe depois de corrigido)
aumentava o subtotal sem aumentar a taxa. O total do servidor deixava de ser
"subtotal + aliquota" e ficava MENOR do que o PDV mostrou e cobrou do cliente.

Esta migration faz as duas coisas: cria `service_fee_percent` e realinha os
pedidos que ainda podem ser cobrados.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations, models

CENTS = Decimal("0.01")


def _round(value):
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def repair_totals(apps, schema_editor):
    """Adota a aliquota do restaurante e refaz taxa e total.

    So mexe em pedido AGUARDANDO PAGAMENTO:

    - pedido pago, cancelado ou estornado e livro fechado — se corrige por
      estorno, nunca por UPDATE de migration;
    - pedido ABERTO ainda nao tem taxa (ela nasce no fechamento). Gravar a
      aliquota ali faria a taxa aparecer no carrinho antes da hora.

    Nenhum cliente envia `service_fee` explicito no fechamento — nem o PDV nem
    a retaguarda — entao adotar o percentual do restaurante nao atropela taxa
    digitada a mao: ela ainda nao existe no banco.
    """
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")
    pending = Order.objects.filter(status="awaiting_payment").select_related("restaurant")
    for order in pending.iterator():
        subtotal = OrderItem.objects.filter(order=order).exclude(
            status__in=["cancelled", "comped"]
        ).aggregate(value=models.Sum("total_price"))["value"] or Decimal("0.00")

        percent = order.restaurant.default_service_fee_percent or Decimal("0.00")
        if not order.service_fee_enabled:
            percent = None
            fee = Decimal("0.00")
        else:
            fee = _round((subtotal * percent) / Decimal("100"))

        total = max(subtotal + fee + order.delivery_fee - order.discount, Decimal("0.00"))
        if (order.subtotal, order.service_fee, order.total, order.service_fee_percent) == (
            subtotal,
            fee,
            total,
            percent,
        ):
            continue
        order.subtotal = subtotal
        order.service_fee = fee
        order.service_fee_percent = percent
        order.total = total
        order.save(update_fields=["subtotal", "service_fee", "service_fee_percent", "total"])


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0005_order_fiscal_customer_cpf"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="service_fee_percent",
            field=models.DecimalField(blank=True, decimal_places=2, default=None, max_digits=5, null=True),
        ),
        migrations.RunPython(repair_totals, migrations.RunPython.noop),
    ]
