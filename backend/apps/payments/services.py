from decimal import Decimal

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


def get_open_cash_register(branch):
    with tenant_context(branch.account):
        return CashRegister.objects.filter(branch=branch, status=CashRegister.STATUS_OPEN).order_by("-opened_at").first()


@transaction.atomic
def open_cash_register(*, branch, user, opening_amount=Decimal("0.00"), notes=""):
    with tenant_context(branch.account):
        existing = get_open_cash_register(branch)
        if existing:
            raise ValidationError("There is already an open cash register for this branch.")

        cash_register = CashRegister.objects.create(
            account=branch.account,
            restaurant=branch.restaurant,
            branch=branch,
            opened_by=user,
            opening_amount=opening_amount,
            expected_amount=opening_amount,
            notes=notes,
            created_by=user,
            updated_by=user,
        )
        CashMovement.objects.create(
            account=branch.account,
            restaurant=branch.restaurant,
            branch=branch,
            cash_register=cash_register,
            operator=user,
            movement_type=CashMovement.TYPE_OPENING,
            amount=opening_amount,
            reason="Opening balance",
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
            raise ValidationError("Cash register is already closed.")

        expected = cash_register.movements.aggregate(value=Sum("amount"))["value"] or Decimal("0.00")
        actual_amount = Decimal(str(actual_amount))
        cash_register.expected_amount = expected
        cash_register.actual_amount = actual_amount
        cash_register.difference_amount = actual_amount - expected
        cash_register.status = CashRegister.STATUS_CLOSED
        cash_register.closed_by = user
        cash_register.closed_at = timezone.now()
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
        record_audit(action=AuditLog.ACTION_UPDATED, instance=cash_register, actor=user, metadata={"event": "close_cash"})
        return cash_register


@transaction.atomic
def register_payment(*, order, user, payment_method_id, amount, idempotency_key=None, metadata=None):
    with tenant_context(order.account):
        if idempotency_key:
            existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing

        order = Order.objects.select_for_update().select_related("branch").get(pk=order.pk)
        if order.status in {Order.STATUS_CANCELLED, Order.STATUS_REFUNDED}:
            raise ValidationError("Cancelled or refunded orders cannot be paid.")
        if order.payment_status == Order.PAYMENT_PAID:
            raise ValidationError("Order has already been paid.")

        payment_method = PaymentMethod.objects.get(pk=payment_method_id, branch=order.branch, is_active=True)
        cash_register = get_open_cash_register(order.branch)
        if order.branch.require_open_cash_register and not cash_register:
            raise ValidationError("Open cash register is required to receive payment.")

        amount = Decimal(str(amount))
        paid_before = order.payments.filter(status=Payment.STATUS_APPROVED).aggregate(value=Sum("amount"))["value"] or Decimal("0.00")
        remaining = order.total - paid_before
        change_amount = max(amount - remaining, Decimal("0.00"))
        accepted_amount = amount - change_amount

        payment = Payment.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            order=order,
            payment_method=payment_method,
            amount=accepted_amount,
            change_amount=change_amount,
            idempotency_key=idempotency_key,
            metadata=metadata or {},
            created_by=user,
            updated_by=user,
        )

        if cash_register:
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
        if paid_total >= order.total:
            order.payment_status = Order.PAYMENT_PAID
            order.status = Order.STATUS_PAID
            order.closed_at = order.closed_at or timezone.now()
            if order.table_id:
                order.table.status = Table.STATUS_FREE
                order.table.current_order_id = None
                order.table.save(update_fields=["status", "current_order_id", "updated_at"])
            if order.branch.stock_deduction_timing == "payment":
                from apps.stock.services import deduct_order_stock

                deduct_order_stock(order=order, user=user)
        else:
            order.payment_status = Order.PAYMENT_PARTIAL

        order.updated_by = user
        order.save(update_fields=["payment_status", "status", "closed_at", "updated_by", "updated_at"])
        record_audit(action=AuditLog.ACTION_PAYMENT, instance=payment, actor=user, metadata={"order": str(order.id)})
        return payment
