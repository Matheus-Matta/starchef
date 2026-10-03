from django.db.models import Q, Sum
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order, OrderItem
from apps.orders.operator_code import codigo_de
from apps.reports.views import TenantReportMixin


class ProductSalesDetailView(TenantReportMixin, APIView):
    """Cada linha vendida do produto, com o atendimento e quem a lançou."""

    def get(self, request, product_id):
        filters = self.tenant_filter()
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        parsed_from = parse_date(date_from) if date_from else None
        parsed_to = parse_date(date_to) if date_to else None
        if (date_from and not parsed_from) or (date_to and not parsed_to):
            return Response(
                {"detail": "Período inválido. Use datas no formato AAAA-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if parsed_from and parsed_to and parsed_from > parsed_to:
            return Response(
                {"detail": "A data inicial não pode ser posterior à data final."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = self.tenant_manager(OrderItem).filter(
            product_id=product_id,
        ).filter(
            Q(order__payment_status=Order.PAYMENT_PAID)
            | Q(order__status=Order.STATUS_PAID),
            **{f"order__{key}": value for key, value in filters.items()},
        ).exclude(status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED])
        if parsed_from:
            queryset = queryset.filter(order__opened_at__date__gte=parsed_from)
        if parsed_to:
            queryset = queryset.filter(order__opened_at__date__lte=parsed_to)

        rows = queryset.values(
            "id", "quantity", "unit_price", "total_price", "metafields",
            "command_item__metafields",
            "launched_by__first_name", "launched_by__last_name", "launched_by__username",
            "order__sequence", "order__order_type", "order__total",
            "order__closed_at", "order__closed_by__first_name",
            "order__closed_by__last_name", "order__closed_by__username",
            "command__number", "command__customer_name", "product__name",
        ).order_by("-order__closed_at", "-id")
        sales = []
        for row in rows:
            metafields = row.pop("metafields") or {}
            command_metafields = row.pop("command_item__metafields") or {}
            seller = " ".join(filter(None, [
                row.pop("launched_by__first_name"), row.pop("launched_by__last_name"),
            ])).strip()
            seller = seller or row.pop("launched_by__username") or "Não identificado"
            cashier = " ".join(filter(None, [
                row.pop("order__closed_by__first_name"), row.pop("order__closed_by__last_name"),
            ])).strip()
            cashier = cashier or row.pop("order__closed_by__username") or "Não identificado"
            sales.append({
                "id": row["id"],
                "product": row["product__name"],
                "quantity": row["quantity"],
                "unit_price": row["unit_price"],
                "item_total": row["total_price"],
                "order_sequence": row["order__sequence"],
                "order_type": row["order__order_type"],
                "order_total": row["order__total"],
                "closed_at": row["order__closed_at"],
                "cashier": cashier,
                "operator": seller,
                "operator_code": codigo_de(metafields) or codigo_de(command_metafields),
                "command_number": row["command__number"],
                "command_name": row["command__customer_name"],
            })
        totals = queryset.aggregate(quantity=Sum("quantity"), total=Sum("total_price"))
        return Response({
            "product": sales[0]["product"] if sales else "Produto",
            "quantity": totals["quantity"] or 0,
            "total": totals["total"] or 0,
            "sales": sales,
        })
