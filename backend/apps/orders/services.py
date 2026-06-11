from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.orders.events import broadcast_kitchen_event
from apps.orders.models import Order, OrderItem
from apps.restaurants.models import Table


def next_order_sequence(branch):
    with tenant_context(branch.account):
        last_sequence = Order.objects.filter(branch=branch).aggregate(value=Max("sequence"))["value"] or 0
        return last_sequence + 1


@transaction.atomic
def create_order(*, restaurant, branch, order_type, user, **kwargs):
    account = branch.account
    if restaurant.account_id != account.id:
        raise ValidationError("Restaurant and branch must belong to the same account.")

    with tenant_context(account):
        if order_type == Order.TYPE_TABLE and kwargs.get("table"):
            table = Table.objects.select_for_update().get(pk=kwargs["table"].pk)
            if table.status == Table.STATUS_OCCUPIED and not table.current_order_id:
                raise ValidationError("Table is inconsistent: occupied without current order.")
            if table.status == Table.STATUS_OCCUPIED:
                raise ValidationError("Table already has an open order.")
            kwargs["table"] = table

        order = Order.objects.create(
            account=account,
            restaurant=restaurant,
            branch=branch,
            sequence=next_order_sequence(branch),
            order_type=order_type,
            responsible_user=user,
            created_by=user,
            updated_by=user,
            **kwargs,
        )

        if order.table_id:
            order.table.status = Table.STATUS_OCCUPIED
            order.table.current_order_id = order.id
            order.table.save(update_fields=["status", "current_order_id", "updated_at"])

        record_audit(action=AuditLog.ACTION_CREATED, instance=order, actor=user)
        return order


@transaction.atomic
def add_order_item(*, order, product, quantity, user, variations=None, customer_note=""):
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)
        if product.account_id != order.account_id:
            raise ValidationError("Product does not belong to the order account.")
        if order.is_locked:
            raise ValidationError("Paid, cancelled or refunded orders cannot be changed.")
        if not product.is_active:
            raise ValidationError("Inactive product cannot be added to an order.")

        quantity = Decimal(str(quantity))
        unit_price = product.current_price
        item = OrderItem.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            order=order,
            product=product,
            quantity=quantity,
            unit_price=unit_price,
            total_price=unit_price * quantity,
            variations=variations or [],
            customer_note=customer_note,
            production_sector=product.production_sector,
            launched_by=user,
            created_by=user,
            updated_by=user,
        )
        recalculate_order(order)
        record_audit(action=AuditLog.ACTION_CREATED, instance=item, actor=user)
        return item


@transaction.atomic
def recalculate_order(order):
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)
        subtotal = order.items.exclude(status=OrderItem.STATUS_CANCELLED).aggregate(value=Sum("total_price"))["value"]
        order.subtotal = subtotal or Decimal("0.00")
        order.total = order.subtotal + order.service_fee + order.delivery_fee - order.discount
        if order.total < Decimal("0.00"):
            order.total = Decimal("0.00")
        order.save(update_fields=["subtotal", "total", "updated_at"])
        return order


@transaction.atomic
def send_order_to_kitchen(order, user):
    with tenant_context(order.account):
        order = Order.objects.select_for_update().prefetch_related("items__product").get(pk=order.pk)
        if order.is_locked:
            raise ValidationError("Locked orders cannot be sent to kitchen.")

        now = timezone.now()
        items = order.items.filter(status=OrderItem.STATUS_PENDING)
        for item in items:
            item.status = OrderItem.STATUS_SENT
            item.sent_to_kitchen_at = now
            item.updated_by = user
            item.save(update_fields=["status", "sent_to_kitchen_at", "updated_by", "updated_at"])
            broadcast_kitchen_event(
                order.account_id,
                order.branch_id,
                item.production_sector,
                "order_item.sent",
                serialize_kitchen_item(item),
            )

        order.status = Order.STATUS_SENT_TO_KITCHEN
        order.updated_by = user
        order.save(update_fields=["status", "updated_by", "updated_at"])
        record_audit(action=AuditLog.ACTION_UPDATED, instance=order, actor=user, metadata={"event": "send_to_kitchen"})

        if order.branch.stock_deduction_timing == "kitchen":
            from apps.stock.services import deduct_order_stock

            deduct_order_stock(order=order, user=user)

        return order


@transaction.atomic
def update_order_item_status(item, status, user, reason=""):
    with tenant_context(item.account):
        item = OrderItem.objects.select_for_update().select_related("order").get(pk=item.pk)
        if item.order.is_locked:
            raise ValidationError("Items from paid, cancelled or refunded orders cannot be changed.")
        if item.status == OrderItem.STATUS_READY and status != OrderItem.STATUS_DELIVERED:
            profile = getattr(user, "profile", None)
            if not profile or profile.profile_type not in {"admin", "owner", "manager"}:
                raise ValidationError("Ready items require manager permission to change.")
        if status == OrderItem.STATUS_CANCELLED and not reason:
            raise ValidationError("Cancellation reason is required.")

        now = timezone.now()
        item.status = status
        item.updated_by = user
        if status == OrderItem.STATUS_PREPARING:
            item.preparation_started_at = now
        elif status == OrderItem.STATUS_READY:
            item.ready_at = now
        elif status == OrderItem.STATUS_DELIVERED:
            item.delivered_at = now
        elif status == OrderItem.STATUS_CANCELLED:
            item.cancel_reason = reason

        item.save()
        recalculate_order(item.order)
        sync_order_status_from_items(item.order)
        record_audit(action=AuditLog.ACTION_UPDATED, instance=item, actor=user, reason=reason, metadata={"status": status})
        broadcast_kitchen_event(
            item.account_id,
            item.branch_id,
            item.production_sector,
            "order_item.status_changed",
            serialize_kitchen_item(item),
        )
        return item


@transaction.atomic
def close_order(order, user, *, discount=Decimal("0.00"), service_fee=None):
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.is_locked:
            raise ValidationError("Locked orders cannot be closed.")
        if discount and discount > Decimal("0.00"):
            profile = getattr(user, "profile", None)
            if not profile or profile.profile_type not in {"admin", "owner", "manager"}:
                raise ValidationError("Discount requires manager permission.")

        order.discount = Decimal(str(discount or 0))
        if service_fee is not None:
            order.service_fee = Decimal(str(service_fee))
        elif order.branch.default_service_fee_percent:
            order.service_fee = (order.subtotal * order.branch.default_service_fee_percent) / Decimal("100")
        order.status = Order.STATUS_AWAITING_PAYMENT
        order.closed_by = user
        order.updated_by = user
        order.closed_at = timezone.now()
        order.save(update_fields=["discount", "service_fee", "status", "closed_by", "closed_at", "updated_by", "updated_at"])
        order = recalculate_order(order)
        record_audit(action=AuditLog.ACTION_UPDATED, instance=order, actor=user, metadata={"event": "close_order"})
        return order


@transaction.atomic
def cancel_order(order, user, reason):
    if not reason:
        raise ValidationError("Cancellation reason is required.")
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status == Order.STATUS_PAID:
            raise ValidationError("Paid orders must be refunded instead of cancelled.")
        order.status = Order.STATUS_CANCELLED
        order.cancel_reason = reason
        order.updated_by = user
        order.save(update_fields=["status", "cancel_reason", "updated_by", "updated_at"])
        order.items.exclude(status=OrderItem.STATUS_CANCELLED).update(status=OrderItem.STATUS_CANCELLED, cancel_reason=reason)
        if order.table_id:
            order.table.status = Table.STATUS_FREE
            order.table.current_order_id = None
            order.table.save(update_fields=["status", "current_order_id", "updated_at"])
        record_audit(action=AuditLog.ACTION_CANCELLED, instance=order, actor=user, reason=reason)
        return order


def sync_order_status_from_items(order):
    with tenant_context(order.account):
        order = Order.objects.get(pk=order.pk)
        active_items = list(order.items.exclude(status=OrderItem.STATUS_CANCELLED).values_list("status", flat=True))
        if not active_items:
            return order
        if all(status == OrderItem.STATUS_READY for status in active_items):
            order.status = Order.STATUS_READY
        elif any(status == OrderItem.STATUS_READY for status in active_items):
            order.status = Order.STATUS_PARTIALLY_READY
        elif any(status == OrderItem.STATUS_PREPARING for status in active_items):
            order.status = Order.STATUS_PREPARING
        order.save(update_fields=["status", "updated_at"])
        return order


def serialize_kitchen_item(item):
    order = item.order
    return {
        "id": str(item.id),
        "account_id": str(item.account_id),
        "order_id": str(order.id),
        "order_sequence": order.sequence,
        "order_type": order.order_type,
        "table": order.table.number if order.table_id else None,
        "command": order.command.code if order.command_id else None,
        "customer": order.customer.name if order.customer_id else None,
        "product": item.product.name,
        "quantity": str(item.quantity),
        "note": item.customer_note,
        "variations": item.variations,
        "status": item.status,
        "production_sector": item.production_sector,
        "sent_to_kitchen_at": item.sent_to_kitchen_at.isoformat() if item.sent_to_kitchen_at else None,
        "elapsed_from": item.sent_to_kitchen_at.isoformat() if item.sent_to_kitchen_at else item.launched_at.isoformat(),
    }
