import hashlib
import hmac
from decimal import Decimal

from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.orders.models import Order
from apps.payments.models import CashMovement, CashRegister, Payment, PaymentMethod
from apps.restaurants.models import Table


def get_open_cash_register(restaurant, user=None, station=None):
    with tenant_context(restaurant.account):
        qs = CashRegister.objects.filter(restaurant=restaurant, status=CashRegister.STATUS_OPEN)
        if user is not None:
            qs = qs.filter(opened_by=user)
        if station:
            qs = qs.filter(station=station)
        return qs.order_by("-opened_at").first()


@transaction.atomic
def open_cash_register(
    *,
    restaurant=None,
    user,
    opening_amount=Decimal("0.00"),
    notes="",
    station="PDV principal",
    device_identifier="",
    branch=None,
    cash_station=None,
):
    # `branch` existe apenas para compatibilidade durante a migração; todo o
    # escopo operacional é resolvido pelo restaurante.
    restaurant = restaurant or getattr(branch, "restaurant", None)
    if restaurant is None:
        raise ValidationError("Informe o restaurante do caixa.")
    if cash_station is not None:
        if cash_station.restaurant_id != restaurant.id or not cash_station.is_active:
            raise ValidationError("O caixa selecionado não pertence ao restaurante ou está inativo.")
        if not cash_station.operators.filter(pk=user.pk).exists():
            raise ValidationError("O operador não está vinculado a este caixa.")
        station = cash_station.name
    with tenant_context(restaurant.account):
        existing = (
            CashRegister.objects.filter(restaurant=restaurant, cash_station=cash_station)
            .exclude(
                status__in=[
                    CashRegister.STATUS_CLOSED,
                    CashRegister.STATUS_CLOSED_DIFFERENCE,
                    CashRegister.STATUS_CANCELLED,
                ]
            )
            .first()
        )
        if existing:
            raise ValidationError("Já existe uma sessão aberta para este caixa.")
        operator_session = (
            CashRegister.objects.filter(restaurant=restaurant, opened_by=user)
            .exclude(
                status__in=[
                    CashRegister.STATUS_CLOSED,
                    CashRegister.STATUS_CLOSED_DIFFERENCE,
                    CashRegister.STATUS_CANCELLED,
                ]
            )
            .select_related("cash_station")
            .first()
        )
        if operator_session:
            current_name = (
                operator_session.cash_station.name if operator_session.cash_station else operator_session.station
            )
            raise ValidationError(
                f"Você já possui uma sessão em andamento no caixa {current_name}. Feche-a antes de abrir outro caixa."
            )

        counted = Decimal(str(opening_amount))
        previous = (
            CashRegister.objects.filter(
                restaurant=restaurant,
                cash_station=cash_station,
                status__in=[CashRegister.STATUS_CLOSED, CashRegister.STATUS_CLOSED_DIFFERENCE],
            )
            .order_by("-closed_at")
            .first()
        )
        expected = previous.actual_amount if previous and previous.actual_amount is not None else counted
        is_initial = previous is None
        matches = counted == expected
        cash_register = CashRegister.objects.create(
            account=restaurant.account,
            restaurant=restaurant,
            opened_by=user,
            station=station,
            cash_station=cash_station,
            device_identifier=device_identifier,
            opening_amount=counted,
            expected_amount=expected,
            actual_amount=counted,
            difference_amount=counted - expected,
            opening_is_initial=is_initial,
            status=CashRegister.STATUS_OPEN if (is_initial or matches) else CashRegister.STATUS_PENDING_APPROVAL,
            pending_operation="" if (is_initial or matches) else "opening",
            notes=notes,
            created_by=user,
            updated_by=user,
        )
        CashMovement.objects.create(
            account=restaurant.account,
            restaurant=restaurant,
            cash_register=cash_register,
            operator=user,
            movement_type=CashMovement.TYPE_OPENING,
            amount=counted,
            reason="Saldo inicial criado" if is_initial else "Conferência cega de abertura",
            metadata={"event": "INITIAL_BALANCE_CREATED"} if is_initial else {},
            created_by=user,
            updated_by=user,
        )
        record_audit(action=AuditLog.ACTION_CREATED, instance=cash_register, actor=user)
        return cash_register


@transaction.atomic
def close_cash_register(*, cash_register, user, actual_amount, notes=""):
    with tenant_context(cash_register.account):
        cash_register = CashRegister.objects.select_for_update().get(pk=cash_register.pk)
        if cash_register.status == CashRegister.STATUS_CLOSED:
            raise ValidationError("O caixa já está fechado.")

        expected = cash_register.movements.filter(status="approved").aggregate(value=Sum("amount"))["value"] or Decimal(
            "0.00"
        )
        actual_amount = Decimal(str(actual_amount))
        cash_register.expected_amount = expected
        cash_register.actual_amount = actual_amount
        cash_register.difference_amount = actual_amount - expected
        cash_register.status = (
            CashRegister.STATUS_CLOSED if cash_register.difference_amount == 0 else CashRegister.STATUS_PENDING_APPROVAL
        )
        cash_register.pending_operation = "" if cash_register.difference_amount == 0 else "closing"
        cash_register.closed_by = user
        cash_register.closed_at = timezone.now() if cash_register.difference_amount == 0 else None
        cash_register.notes = notes
        cash_register.updated_by = user
        cash_register.save()

        CashMovement.objects.create(
            account=cash_register.account,
            restaurant=cash_register.restaurant,
            branch=cash_register.branch,
            cash_register=cash_register,
            operator=user,
            movement_type=CashMovement.TYPE_CLOSING,
            amount=Decimal("0.00"),
            reason="Cash register closed",
            created_by=user,
            updated_by=user,
        )
        record_audit(
            action=AuditLog.ACTION_UPDATED, instance=cash_register, actor=user, metadata={"event": "close_cash"}
        )
        return cash_register


def _require_manager(user):
    profile = getattr(user, "profile", None)
    if not (user.is_superuser or profile and profile.profile_type in {"admin", "owner", "manager"}):
        raise ValidationError("Esta operação exige um gerente ou supervisor.")


def _is_account_owner(user):
    """O dono da conta (owner) — ou superusuário da plataforma — pode aprovar a
    própria divergência/sangria, dispensando a validação de segregação."""
    profile = getattr(user, "profile", None)
    return bool(user.is_superuser or (profile and profile.profile_type == "owner"))


@transaction.atomic
def create_cash_movement(*, cash_register, user, movement_type, amount, reason, destination=""):
    with tenant_context(cash_register.account):
        cash_register = CashRegister.objects.select_for_update().get(pk=cash_register.pk)
        if cash_register.status != CashRegister.STATUS_OPEN:
            raise ValidationError("O caixa precisa estar aberto para registrar movimentações.")
        amount = Decimal(str(amount))
        if amount <= 0 or not reason.strip():
            raise ValidationError("Informe um valor maior que zero e o motivo.")
        needs_approval = movement_type in {CashMovement.TYPE_WITHDRAWAL, CashMovement.TYPE_SUPPLY}
        movement = CashMovement.objects.create(
            account=cash_register.account,
            restaurant=cash_register.restaurant,
            branch=cash_register.branch,
            cash_register=cash_register,
            operator=user,
            movement_type=movement_type,
            amount=-amount if movement_type == CashMovement.TYPE_WITHDRAWAL else amount,
            reason=reason,
            destination=destination,
            status="pending" if needs_approval else "approved",
            created_by=user,
            updated_by=user,
        )
        record_audit(action=AuditLog.ACTION_CREATED, instance=movement, actor=user, metadata={"event": movement_type})
        return movement


@transaction.atomic
def _cash_password_proof(stored_hash, cash_register_id, nonce):
    """HMAC do hash da senha do caixa sobre a operação — ver docstring acima."""
    return hmac.new(
        str(stored_hash or "").encode("utf-8"),
        f"{cash_register_id}:{nonce}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def approve_cash_operation(
    *,
    cash_register,
    user,
    reason,
    movement=None,
    cash_password=None,
    cash_password_proof=None,
    proof_nonce="",
):
    """Autoriza uma divergência de caixa ou uma movimentação pendente.

    A autorização por SENHA do caixa (definida no restaurante) substitui a
    exigência de um gerente logado — habilita a autorização mesmo sem outro
    gerente presente. Sem senha nem prova → exige gerente, como antes.

    ``cash_password_proof`` existe para o PDV que autorizou **offline**. O
    terminal guarda o hash PBKDF2 da senha (é assim que ele já verifica sem
    rede) e prova que o possui devolvendo um HMAC-SHA256 desse hash sobre
    ``{cash_register_id}:{proof_nonce}``. Assim a senha em texto nunca é
    gravada na fila local nem trafega no replay — guardá-la em disco seria pior
    do que a espera que a autorização offline evita.
    """
    authorized_by_password = False
    if cash_password_proof:
        stored = cash_register.restaurant.cash_action_password
        expected = _cash_password_proof(stored, cash_register.pk, proof_nonce)
        if not stored or not hmac.compare_digest(expected, str(cash_password_proof)):
            raise ValidationError("Autorização offline do caixa não pôde ser verificada.")
        authorized_by_password = True
    elif cash_password:
        stored = cash_register.restaurant.cash_action_password
        if not stored or not check_password(cash_password, stored):
            raise ValidationError("Senha de ações do caixa inválida.")
        authorized_by_password = True
    else:
        _require_manager(user)

    if not reason.strip():
        raise ValidationError("A justificativa gerencial é obrigatória.")
    with tenant_context(cash_register.account):
        cash_register = CashRegister.objects.select_for_update().get(pk=cash_register.pk)
        if movement:
            movement = CashMovement.objects.select_for_update().get(pk=movement.pk, cash_register=cash_register)
            # A senha do restaurante já é a autorização — dispensa a segregação operador≠aprovador.
            if not authorized_by_password and movement.operator_id == user.id and not _is_account_owner(user):
                raise ValidationError("O operador não pode aprovar a própria sangria.")
            movement.status = "approved"
            movement.authorized_by = user
            movement.approved_at = timezone.now()
            movement.metadata = {
                **movement.metadata,
                "manager_reason": reason,
                "authorized_by_cash_password": authorized_by_password,
            }
            movement.save()
            return movement
        if not authorized_by_password and cash_register.opened_by_id == user.id and not _is_account_owner(user):
            raise ValidationError("O operador não pode aprovar a própria divergência.")
        cash_register.approved_by = user
        cash_register.approved_at = timezone.now()
        cash_register.approval_reason = reason
        cash_register.status = (
            CashRegister.STATUS_OPEN
            if cash_register.pending_operation == "opening"
            else CashRegister.STATUS_CLOSED_DIFFERENCE
        )
        if cash_register.status == CashRegister.STATUS_CLOSED_DIFFERENCE:
            cash_register.closed_at = timezone.now()
            cash_register.closed_by = user
        cash_register.pending_operation = ""
        cash_register.save()
        return cash_register


@transaction.atomic
def register_payment(
    *,
    order,
    user,
    payment_method_id,
    amount,
    idempotency_key=None,
    metadata=None,
    cash_register_id=None,
):
    with tenant_context(order.account):
        if idempotency_key:
            existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing

        # PostgreSQL rejeita FOR UPDATE quando o JOIN inclui o lado nullable.
        # O `of` mantém o eager loading, mas restringe o lock ao pedido.
        order = Order.objects.select_related("branch").select_for_update(of=("self",)).get(pk=order.pk)
        if order.status in {Order.STATUS_CANCELLED, Order.STATUS_REFUNDED}:
            raise ValidationError("Pedidos cancelados ou estornados não podem ser pagos.")
        if order.payment_status == Order.PAYMENT_PAID:
            raise ValidationError("O pedido já foi pago.")

        payment_method = PaymentMethod.objects.get(pk=payment_method_id, restaurant=order.restaurant, is_active=True)
        if cash_register_id:
            cash_register = CashRegister.objects.filter(
                pk=cash_register_id,
                restaurant=order.restaurant,
                opened_by=user,
                status=CashRegister.STATUS_OPEN,
            ).first()
            if cash_register is None:
                raise ValidationError(
                    "A sessão de caixa usada neste pagamento não está mais aberta "
                    "para este operador. Revise a venda antes de sincronizar."
                )
        else:
            cash_register = get_open_cash_register(order.restaurant, user=user)
        if order.restaurant.require_open_cash_register and not cash_register:
            raise ValidationError("É necessário ter um caixa aberto para receber o pagamento.")

        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValidationError("Informe um valor de pagamento maior que zero.")
        paid_before = order.payments.filter(status=Payment.STATUS_APPROVED).aggregate(value=Sum("amount"))[
            "value"
        ] or Decimal("0.00")
        remaining = order.total - paid_before
        if payment_method.method_type != PaymentMethod.TYPE_CASH and amount > remaining:
            raise ValidationError("Somente pagamentos em dinheiro podem ter valor recebido maior que o restante.")
        change_amount = max(amount - remaining, Decimal("0.00"))
        accepted_amount = amount - change_amount
        payment_metadata = {
            **(metadata or {}),
            "received_amount": str(amount),
            "applied_amount": str(accepted_amount),
            "change_amount": str(change_amount),
        }

        payment = Payment.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            order=order,
            payment_method=payment_method,
            amount=accepted_amount,
            change_amount=change_amount,
            idempotency_key=idempotency_key,
            metadata=payment_metadata,
            created_by=user,
            updated_by=user,
        )

        if cash_register and payment_method.method_type == PaymentMethod.TYPE_CASH:
            CashMovement.objects.create(
                account=order.account,
                restaurant=order.restaurant,
                branch=order.branch,
                cash_register=cash_register,
                payment=payment,
                operator=user,
                movement_type=CashMovement.TYPE_SALE,
                amount=accepted_amount,
                reason=f"Order {order.sequence} payment",
                created_by=user,
                updated_by=user,
            )

        paid_total = paid_before + accepted_amount
        paid_in_full = paid_total >= order.total
        if paid_in_full:
            order.payment_status = Order.PAYMENT_PAID
            order.status = Order.STATUS_PAID
            order.closed_at = order.closed_at or timezone.now()
        else:
            order.payment_status = Order.PAYMENT_PARTIAL

        order.updated_by = user
        order.save(update_fields=["payment_status", "status", "closed_at", "updated_by", "updated_at"])

        if paid_in_full:
            if order.table_id:
                from apps.orders.services import free_table_if_empty

                free_table_if_empty(order.table)
            # Comanda: zera e libera para reuso (padrao self-service).
            from apps.orders.services import free_command_for_order

            free_command_for_order(order)
            if order.restaurant.stock_deduction_timing == "payment":
                from apps.stock.services import deduct_order_stock

                deduct_order_stock(order=order, user=user)

        record_audit(action=AuditLog.ACTION_PAYMENT, instance=payment, actor=user, metadata={"order": str(order.id)})
        return payment


@transaction.atomic
def cancel_payment(*, payment, user):
    """Cancela um recebimento lançado no PDV e desfaz seus efeitos operacionais."""
    with tenant_context(payment.account):
        payment = (
            Payment.objects.select_related("order__restaurant", "order__table", "order__command")
            .select_for_update(of=("self",))
            .get(pk=payment.pk)
        )
        if payment.status != Payment.STATUS_APPROVED:
            raise ValidationError("Este pagamento já foi cancelado ou estornado.")

        order = (
            Order.objects.select_related("restaurant", "table", "command")
            .select_for_update(of=("self",))
            .get(pk=payment.order_id)
        )
        was_paid = order.payment_status == Order.PAYMENT_PAID

        payment.status = Payment.STATUS_CANCELLED
        payment.updated_by = user
        payment.save(update_fields=["status", "updated_by", "updated_at"])
        payment.cash_movements.filter(status="approved").update(status="cancelled", updated_by=user)

        paid_total = order.payments.filter(status=Payment.STATUS_APPROVED).aggregate(value=Sum("amount"))[
            "value"
        ] or Decimal("0.00")
        order.payment_status = Order.PAYMENT_PARTIAL if paid_total > 0 else Order.PAYMENT_PENDING
        order.status = Order.STATUS_AWAITING_PAYMENT
        order.closed_at = None
        order.updated_by = user
        order.save(update_fields=["payment_status", "status", "closed_at", "updated_by", "updated_at"])

        if was_paid:
            if order.order_type == Order.TYPE_TABLE and order.table_id:
                # Apenas para reabrir registros legados; novas vendas de salão
                # são sempre comandas vinculadas a uma mesa.
                table = Table.objects.select_for_update().get(pk=order.table_id)
                table.status = Table.STATUS_OCCUPIED
                table.current_order_id = order.id
                table.save(update_fields=["status", "current_order_id", "updated_at"])
            if order.command_id:
                from apps.restaurants.models import Command

                command = Command.objects.select_for_update().get(pk=order.command_id)
                command.status = Command.STATUS_OCCUPIED
                command.current_order_id = order.id
                command.customer_name = order.customer.name if order.customer_id else ""
                command.current_table = order.table
                command.save(
                    update_fields=[
                        "status",
                        "current_order_id",
                        "customer_name",
                        "current_table",
                        "updated_at",
                    ]
                )
                if order.table_id:
                    table = Table.objects.select_for_update().get(pk=order.table_id)
                    table.status = Table.STATUS_OCCUPIED
                    table.current_order_id = None
                    table.save(update_fields=["status", "current_order_id", "updated_at"])

            if order.restaurant.stock_deduction_timing == "payment":
                from apps.stock.models import StockMovement

                stock_effects = (
                    StockMovement.objects.filter(
                        order_item__order=order,
                        reason__in=[
                            f"Auto deduction from order {order.sequence}",
                            f"Payment cancellation from order {order.sequence}",
                        ],
                    )
                    .values("account", "restaurant", "branch", "ingredient", "location", "order_item", "unit_cost")
                    .annotate(quantity_total=Sum("quantity"), cost_total=Sum("total_cost"))
                )
                for effect in stock_effects:
                    if not effect["quantity_total"] and not effect["cost_total"]:
                        continue
                    StockMovement.objects.create(
                        account_id=effect["account"],
                        restaurant_id=effect["restaurant"],
                        branch_id=effect["branch"],
                        ingredient_id=effect["ingredient"],
                        location_id=effect["location"],
                        order_item_id=effect["order_item"],
                        operator=user,
                        movement_type=StockMovement.TYPE_ADJUSTMENT,
                        quantity=-effect["quantity_total"],
                        unit_cost=effect["unit_cost"],
                        total_cost=-effect["cost_total"],
                        reason=f"Payment cancellation from order {order.sequence}",
                        created_by=user,
                        updated_by=user,
                    )

        record_audit(
            action=AuditLog.ACTION_CANCELLED,
            instance=payment,
            actor=user,
            metadata={"order": str(order.id), "event": "payment_cancelled"},
        )
        return payment
