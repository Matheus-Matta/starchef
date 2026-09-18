"""Builds the complete auditable statement of one cash-register session."""

from apps.orders.models import Order
from apps.payments.serializers import CashRegisterSerializer
from apps.payments.terminals import operator_label


def _order_reference(order):
    if order.table_id:
        return f"Mesa {order.table.number}"
    if order.command_id:
        return f"Comanda {order.command.code}"
    return f"Pedido #{order.sequence}"


def _item_data(item):
    return {
        "id": str(item.pk),
        "product_name": item.product.name,
        "quantity": item.quantity,
        "unit_price": item.unit_price,
        "total_price": item.total_price,
        "status": item.status,
        "production_sector": item.production_sector,
        "customer_note": item.customer_note,
        "void_reason": item.void_reason,
        "variations": item.variations,
        "addons": [
            {
                "name": addon.addon.name,
                "quantity": addon.quantity,
                "unit_price": addon.unit_price,
                "total_price": addon.total_price,
            }
            for addon in item.addons.all()
        ],
    }


def cash_session_statement(session, *, context=None):
    """Return the session, receipts and sold items without client-side N+1 calls."""
    session_data = CashRegisterSerializer(session, context=context or {}).data
    order_ids = {sale["order"] for sale in session_data["sales"] if sale.get("order")}
    orders = (
        Order.objects.filter(pk__in=order_ids)
        .select_related("table", "command", "responsible_user", "closed_by")
        .prefetch_related("items__product", "items__addons__addon")
        .order_by("opened_at")
    )
    return {
        "session": session_data,
        "orders": [
            {
                "id": str(order.pk),
                "sequence": order.sequence,
                "reference": _order_reference(order),
                "order_type": order.order_type,
                "status": order.status,
                "payment_status": order.payment_status,
                "opened_at": order.opened_at,
                "closed_at": order.closed_at,
                "operator_name": operator_label(order.responsible_user),
                "closed_by_name": operator_label(order.closed_by) if order.closed_by_id else "",
                "subtotal": order.subtotal,
                "service_fee": order.service_fee,
                "discount": order.discount,
                "delivery_fee": order.delivery_fee,
                "total": order.total,
                "notes": order.general_notes,
                "cancel_reason": order.cancel_reason,
                "items": [_item_data(item) for item in order.items.all()],
            }
            for order in orders
        ],
    }
