"""Detalhe dos cancelamentos para o relatorio de pedidos.

Os agregados por motivo continuam em `SalesReportView`; aqui entra o que o
gerente pergunta em seguida: QUAL pedido, QUEM cancelou, QUEM liberou, quando
e quanto — e o mesmo para itens retirados da conta. Le das colunas do pedido
e do item (`cancelled_*`, `voided_*`), preenchidas no cancelamento e
retroalimentadas da auditoria pela migracao 0008.
"""

import csv

from django.db.models import Count, Sum
from django.db.models.functions import ExtractHour
from django.http import HttpResponse

from apps.orders.models import Order, OrderItem

AUTHORIZATION_LABELS = {
    Order.AUTHORIZATION_OWN: "Própria",
    Order.AUTHORIZATION_CASH_PASSWORD: "Senha do caixa",
    Order.AUTHORIZATION_DELEGATED: "Usuário autorizado",
    Order.AUTHORIZATION_GRACE: "Dentro da carência",
    "": "Não registrada",
}

ORDER_TYPE_LABELS = {
    "table": "Mesa",
    "command": "Comanda",
    "counter": "Balcão",
    "delivery": "Entrega",
    "takeaway": "Retirada",
    "internal": "Consumo interno",
}


def _name(first, last, username):
    return f"{first or ''} {last or ''}".strip() or (username or "")


def cancellation_details(*, all_orders, item_queryset, request):
    """Listas e KPIs de cancelamento para o periodo ja filtrado."""
    cancelled = all_orders.filter(status=Order.STATUS_CANCELLED).select_related(
        "cancelled_by", "cancel_authorized_by", "table", "command", "customer"
    )
    cancelled_by = request.query_params.get("cancelled_by")
    authorization = request.query_params.get("authorization")
    order_type = request.query_params.get("order_type")
    if cancelled_by:
        cancelled = cancelled.filter(cancelled_by_id=cancelled_by)
    if authorization:
        cancelled = cancelled.filter(cancel_authorization=authorization)
    if order_type:
        cancelled = cancelled.filter(order_type=order_type)

    cancelled_orders = []
    for order in cancelled.order_by("-cancelled_at", "-opened_at"):
        opened_for = None
        if order.cancelled_at and order.opened_at:
            opened_for = int((order.cancelled_at - order.opened_at).total_seconds() // 60)
        cancelled_orders.append(
            {
                "id": str(order.pk),
                "sequence": order.sequence,
                "order_type": order.order_type,
                "order_type_label": ORDER_TYPE_LABELS.get(order.order_type, order.order_type),
                "reference": _reference(order),
                "opened_at": order.opened_at,
                "cancelled_at": order.cancelled_at,
                "minutes_open": opened_for,
                "cancelled_by": _name(
                    getattr(order.cancelled_by, "first_name", ""),
                    getattr(order.cancelled_by, "last_name", ""),
                    getattr(order.cancelled_by, "username", ""),
                ),
                "authorized_by": _name(
                    getattr(order.cancel_authorized_by, "first_name", ""),
                    getattr(order.cancel_authorized_by, "last_name", ""),
                    getattr(order.cancel_authorized_by, "username", ""),
                ),
                "authorization": order.cancel_authorization,
                "authorization_label": AUTHORIZATION_LABELS.get(order.cancel_authorization, order.cancel_authorization),
                "reason": order.cancel_reason or "Motivo não informado",
                "total": order.total,
                "items_count": order.items.count(),
            }
        )

    voided = (
        item_queryset.filter(status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED])
        .exclude(order__status=Order.STATUS_CANCELLED)
        .select_related("order", "product", "voided_by")
        .order_by("-voided_at", "-updated_at")
    )
    if cancelled_by:
        voided = voided.filter(voided_by_id=cancelled_by)
    voided_items = [
        {
            "id": str(item.pk),
            "order_id": str(item.order_id),
            "order_sequence": item.order.sequence,
            "product_name": item.product.name if item.product_id else "Produto removido",
            "quantity": item.quantity,
            "total_price": item.total_price,
            "kind": "Cortesia" if item.status == OrderItem.STATUS_COMPED else "Desistência",
            "status": item.status,
            "reason": item.void_reason or "Motivo não informado",
            "voided_by": _name(
                getattr(item.voided_by, "first_name", ""),
                getattr(item.voided_by, "last_name", ""),
                getattr(item.voided_by, "username", ""),
            ),
            "voided_at": item.voided_at,
            # Antes de ir a producao: nunca foi enviado (ou saiu ainda na carencia).
            "before_kitchen": item.sent_to_kitchen_at is None,
        }
        for item in voided
    ]

    cancelled_by_user = [
        {
            "user": row["cancelled_by_id"],
            "name": _name(row["cancelled_by__first_name"], row["cancelled_by__last_name"], row["cancelled_by__username"]) or "Não identificado",
            "count": row["count"],
            "total": row["total"] or 0,
        }
        for row in cancelled.values("cancelled_by_id", "cancelled_by__first_name", "cancelled_by__last_name", "cancelled_by__username")
        .annotate(count=Count("id"), total=Sum("total"))
        .order_by("-count")
    ]
    cancelled_by_hour = [
        {"hour": row["hour"], "count": row["count"], "total": row["total"] or 0}
        for row in cancelled.filter(cancelled_at__isnull=False)
        .annotate(hour=ExtractHour("cancelled_at"))
        .values("hour")
        .annotate(count=Count("id"), total=Sum("total"))
        .order_by("hour")
    ]
    cancelled_by_authorization = [
        {
            "authorization": row["cancel_authorization"],
            "label": AUTHORIZATION_LABELS.get(row["cancel_authorization"], row["cancel_authorization"]),
            "count": row["count"],
            "total": row["total"] or 0,
        }
        for row in cancelled.values("cancel_authorization").annotate(count=Count("id"), total=Sum("total")).order_by("-count")
    ]

    totals = cancelled.aggregate(total=Sum("total"), count=Count("id"))
    orders_total = all_orders.count()
    voided_totals = voided.aggregate(total=Sum("total_price"), count=Count("id"))
    return {
        "cancelled_orders": cancelled_orders,
        "voided_items": voided_items,
        "cancelled_by_user": cancelled_by_user,
        "cancelled_by_hour": cancelled_by_hour,
        "cancelled_by_authorization": cancelled_by_authorization,
        "cancelled_total": totals["total"] or 0,
        "cancelled_rate": round((totals["count"] or 0) * 100 / orders_total, 2) if orders_total else 0,
        "voided_items_count": voided_totals["count"] or 0,
        "voided_items_total": voided_totals["total"] or 0,
    }


def _reference(order):
    if order.order_type == Order.TYPE_TABLE and order.table_id:
        return f"Mesa {order.table.number}"
    if order.order_type == Order.TYPE_COMMAND and order.command_id:
        return f"Comanda {order.command.code or order.command.number}"
    if order.customer_id:
        return order.customer.name
    return ""


def cancellations_csv(data, date_from, date_to):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="pedidos_cancelamentos_{date_from or "inicio"}_{date_to or "hoje"}.csv"'
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["StarChef — Pedidos e cancelamentos"])
    writer.writerow([f"Período: {date_from or 'início'} a {date_to or 'hoje'}"])
    writer.writerow(["Pedidos no período", data["orders_total"], "Cancelados", data["orders_cancelled"], "Valor cancelado", data["cancelled_total"], "Taxa (%)", data["cancelled_rate"]])
    writer.writerow([])
    writer.writerow(["Pedidos cancelados"])
    writer.writerow(["Pedido", "Tipo", "Referência", "Aberto em", "Cancelado em", "Minutos aberto", "Cancelado por", "Autorização", "Autorizado por", "Motivo", "Itens", "Valor"])
    for row in data["cancelled_orders"]:
        writer.writerow(
            [
                row["sequence"], row["order_type_label"], row["reference"], row["opened_at"], row["cancelled_at"], row["minutes_open"] if row["minutes_open"] is not None else "",
                row["cancelled_by"], row["authorization_label"], row["authorized_by"], row["reason"], row["items_count"], row["total"],
            ]
        )
    writer.writerow([])
    writer.writerow(["Itens retirados da conta"])
    writer.writerow(["Pedido", "Produto", "Qtd", "Valor", "Tipo", "Motivo", "Retirado por", "Quando", "Antes da cozinha"])
    for row in data["voided_items"]:
        writer.writerow(
            [
                row["order_sequence"], row["product_name"], row["quantity"], row["total_price"], row["kind"], row["reason"],
                row["voided_by"], row["voided_at"], "sim" if row["before_kitchen"] else "não",
            ]
        )
    return response
