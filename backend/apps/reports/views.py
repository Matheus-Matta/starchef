import csv
from calendar import monthrange
from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import is_tenant_admin
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment
from apps.stock.models import StockMovement


class TenantReportMixin:
    def tenant_manager(self, model):
        account = getattr(self.request, "account", None)
        if self.request.user.is_superuser and account is None and hasattr(model, "all_objects"):
            return model.all_objects
        return model.objects

    def tenant_filter(self):
        user = self.request.user
        account = getattr(self.request, "account", None)
        if user.is_superuser and account is None:
            return {}
        if account:
            filters = {"account_id": account.id}
        else:
            return {"account_id": None}
        if is_tenant_admin(user):
            restaurant_id = self.request.query_params.get("restaurant")
            branch_id = self.request.query_params.get("branch")
            if restaurant_id:
                filters["restaurant_id"] = restaurant_id
            if branch_id:
                filters["branch_id"] = branch_id
            return filters
        profile = getattr(user, "profile", None)
        if not profile or not profile.restaurant_id:
            return {"account_id": None}
        filters["restaurant_id"] = profile.restaurant_id
        if profile.branch_id:
            filters["branch_id"] = profile.branch_id
        return filters


class DashboardReportView(TenantReportMixin, APIView):
    def get(self, request):
        today = timezone.localdate()
        filters = self.tenant_filter()
        orders = self.tenant_manager(Order).filter(opened_at__date=today, **filters)
        paid_orders = orders.filter(payment_status=Order.PAYMENT_PAID)
        paid_orders_last_7_days = self.tenant_manager(Order).filter(
            opened_at__date__gte=today - timedelta(days=6),
            opened_at__date__lte=today,
            payment_status=Order.PAYMENT_PAID,
            **filters,
        )
        month_start = today.replace(day=1)
        paid_orders_current_month = self.tenant_manager(Order).filter(
            opened_at__date__gte=month_start,
            opened_at__date__lte=today,
            payment_status=Order.PAYMENT_PAID,
            **filters,
        )

        top_products = (
            self.tenant_manager(OrderItem)
            .filter(order__opened_at__date=today, order__payment_status=Order.PAYMENT_PAID, **filters)
            .values("product__name")
            .annotate(quantity=Sum("quantity"), total=Sum("total_price"))
            .order_by("-quantity")[:10]
        )

        # Ingredients whose balance fell below their minimum_stock
        stock_filters = {k: v for k, v in filters.items() if "account" in k or "restaurant" in k or "branch" in k}
        balances = (
            self.tenant_manager(StockMovement)
            .filter(**stock_filters)
            .values("ingredient__name", "ingredient__unit", "ingredient__minimum_stock")
            .annotate(balance=Sum("quantity"))
        )
        low_stock = [
            {
                "ingredient__name": row["ingredient__name"],
                "ingredient__unit": row["ingredient__unit"],
                "balance": row["balance"],
                "minimum_stock": row["ingredient__minimum_stock"],
            }
            for row in balances
            if (row["balance"] or 0) < (row["ingredient__minimum_stock"] or 0)
        ]
        low_stock.sort(key=lambda r: (r["balance"] or 0))

        data = {
            "total_sold_today": paid_orders.aggregate(value=Sum("total"))["value"] or 0,
            "orders_count": orders.count(),
            "open_orders": orders.exclude(status__in=[Order.STATUS_PAID, Order.STATUS_CANCELLED]).count(),
            "kitchen_open_items": self.tenant_manager(OrderItem)
            .filter(**filters)
            .exclude(status__in=[OrderItem.STATUS_DELIVERED, OrderItem.STATUS_CANCELLED])
            .count(),
            "paid_orders": paid_orders.count(),
            "cancelled_orders": orders.filter(status=Order.STATUS_CANCELLED).count(),
            "average_ticket": paid_orders.aggregate(value=Avg("total"))["value"] or 0,
            "sales_today_by_hour": self.sales_today_by_hour(paid_orders, today),
            "sales_last_7_days": self.sales_last_7_days(paid_orders_last_7_days, today),
            "sales_current_month": self.sales_current_month(paid_orders_current_month, today),
            "sales_by_order_type": list(
                paid_orders.values("order_type").annotate(total=Sum("total"), count=Count("id")).order_by("-total")
            ),
            "top_products": list(top_products),
            "low_stock": low_stock[:10],
        }
        return Response(data)

    def sales_today_by_hour(self, queryset, today):
        buckets = [
            {"label": "08h", "start": 8, "end": 10, "total": 0},
            {"label": "10h", "start": 10, "end": 12, "total": 0},
            {"label": "12h", "start": 12, "end": 14, "total": 0},
            {"label": "14h", "start": 14, "end": 16, "total": 0},
            {"label": "16h", "start": 16, "end": 18, "total": 0},
            {"label": "18h", "start": 18, "end": 20, "total": 0},
            {"label": "20h", "start": 20, "end": 22, "total": 0},
            {"label": "22h", "start": 22, "end": 24, "total": 0},
        ]
        rows = queryset.filter(opened_at__date=today).values("opened_at", "total")
        for row in rows:
            hour = timezone.localtime(row["opened_at"]).hour
            for bucket in buckets:
                if bucket["start"] <= hour < bucket["end"]:
                    bucket["total"] += row["total"] or 0
                    break
        return [{"date": today.isoformat(), "label": bucket["label"], "total": bucket["total"]} for bucket in buckets]

    def sales_last_7_days(self, queryset, today):
        totals = {
            row["opened_at__date"]: row["total"] or 0
            for row in queryset.values("opened_at__date").annotate(total=Sum("total"))
        }
        return [
            {
                "date": day.isoformat(),
                "label": day.strftime("%a"),
                "total": totals.get(day, 0),
            }
            for day in [today - timedelta(days=offset) for offset in range(6, -1, -1)]
        ]

    def sales_current_month(self, queryset, today):
        totals = {
            row["opened_at__date"]: row["total"] or 0
            for row in queryset.values("opened_at__date").annotate(total=Sum("total"))
        }
        first_day = today.replace(day=1)
        days_in_month = monthrange(today.year, today.month)[1]
        return [
            {
                "date": day.isoformat(),
                "label": day.strftime("%d"),
                "total": totals.get(day, 0),
            }
            for day in [first_day + timedelta(days=offset) for offset in range(days_in_month)]
        ]


class SalesReportView(TenantReportMixin, APIView):
    report_section = "sales"

    def get(self, request):
        filters = self.tenant_filter()
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        export = request.query_params.get("export")

        parsed_from = parse_date(date_from) if date_from else None
        parsed_to = parse_date(date_to) if date_to else None
        if (date_from and not parsed_from) or (date_to and not parsed_to):
            return Response({"detail": "Período inválido. Use datas no formato AAAA-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        if parsed_from and parsed_to and parsed_from > parsed_to:
            return Response({"detail": "A data inicial não pode ser posterior à data final."}, status=status.HTTP_400_BAD_REQUEST)

        all_orders = self.tenant_manager(Order).filter(**filters)
        if date_from:
            all_orders = all_orders.filter(opened_at__date__gte=parsed_from)
        if date_to:
            all_orders = all_orders.filter(opened_at__date__lte=parsed_to)
        # Imports and older integrations may close an order without mirroring
        # payment_status. A completed order must still appear in revenue reports.
        queryset = all_orders.filter(
            Q(payment_status=Order.PAYMENT_PAID) | Q(status=Order.STATUS_PAID)
        ).distinct()

        payments = self.tenant_manager(Payment).filter(**filters)
        if parsed_from:
            payments = payments.filter(paid_at__date__gte=parsed_from)
        if parsed_to:
            payments = payments.filter(paid_at__date__lte=parsed_to)
        approved_payments = payments.filter(status=Payment.STATUS_APPROVED)

        by_payment = (
            # O cadastro da mesma forma pode existir separadamente em vários
            # restaurantes (e até com tipos internos legados diferentes).
            # Para o relatório consolidado, o nome exibido é a chave: valores
            # de todos os restaurantes devem formar uma única linha.
            approved_payments.values("payment_method__name")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total")
        )
        by_restaurant = (
            queryset.values("restaurant__trade_name")
            # Declare Avg before the "total" annotation alias so Django resolves
            # Order.total instead of trying to average the aggregate alias.
            .annotate(average_ticket=Avg("total"), total=Sum("total"), count=Count("id"))
            .order_by("-total")
        )
        by_waiter = (
            queryset.values(
                "responsible_user__id",
                "responsible_user__first_name",
                "responsible_user__last_name",
                "responsible_user__username",
            )
            .annotate(total=Sum("total"), count=Count("id"))
            .order_by("-total")
        )
        item_filters = {
            key: value
            for key, value in filters.items()
            if key in {"account_id", "restaurant_id", "branch_id"}
        }
        product_dimension_filters = {
            key: value
            for key, value in {
                "product__category_id": request.query_params.get("category"),
                "product__sector_id": request.query_params.get("sector"),
                "product__product_type": request.query_params.get("product_type"),
                "product__production_sector": request.query_params.get("production_sector"),
            }.items()
            if value
        }
        by_product = (
            self.tenant_manager(OrderItem)
            .filter(order__in=queryset, **product_dimension_filters)
            .exclude(status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED])
            .values("product__name")
            .annotate(quantity=Sum("quantity"), total=Sum("total_price"), average_unit_price=Avg("unit_price"))
            .order_by("-total")
        )
        by_status = (
            all_orders.values("status")
            .annotate(count=Count("id"), total=Sum("total"))
            .order_by("-count")
        )
        by_order_type = (
            all_orders.values("order_type")
            .annotate(count=Count("id"), total=Sum("total"))
            .order_by("-count")
        )
        order_cancellation_reasons = (
            all_orders.filter(status=Order.STATUS_CANCELLED)
            .values("cancel_reason")
            .annotate(count=Count("id"), value=Sum("total"))
            .order_by("-count")
        )
        cancelled_items = (
            self.tenant_manager(OrderItem)
            .filter(
                **item_filters,
                status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED],
            )
            .filter(
                **({} if not parsed_from else {"order__opened_at__date__gte": parsed_from}),
                **({} if not parsed_to else {"order__opened_at__date__lte": parsed_to}),
            )
            .values("status", "void_reason")
            .annotate(count=Count("id"), value=Sum("total_price"))
            .order_by("-count")
        )
        cancellation_reasons = [
            {
                "source": "order",
                "kind": "Cancelamento do pedido",
                "reason": row["cancel_reason"] or "Motivo não informado",
                "count": row["count"],
                "value": row["value"] or 0,
            }
            for row in order_cancellation_reasons
        ]
        cancellation_reasons.extend(
            {
                "source": "item",
                "kind": "Cortesia" if row["status"] == OrderItem.STATUS_COMPED else "Desistência de item",
                "reason": row["void_reason"] or "Motivo não informado",
                "count": row["count"],
                "value": row["value"] or 0,
            }
            for row in cancelled_items
        )
        cancellation_reasons.sort(key=lambda row: row["count"], reverse=True)
        paid_totals = queryset.aggregate(
            gross_total=Sum("total"),
            subtotal=Sum("subtotal"),
            discount=Sum("discount"),
            service_fee=Sum("service_fee"),
            delivery_fee=Sum("delivery_fee"),
            average_ticket=Avg("total"),
        )
        product_totals = (
            self.tenant_manager(OrderItem)
            .filter(order__in=queryset, **product_dimension_filters)
            .exclude(status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED])
            .aggregate(quantity=Sum("quantity"), total=Sum("total_price"))
        )

        data = {
            "total": paid_totals["gross_total"] or 0,
            "subtotal": paid_totals["subtotal"] or 0,
            "discount": paid_totals["discount"] or 0,
            "service_fee": paid_totals["service_fee"] or 0,
            "delivery_fee": paid_totals["delivery_fee"] or 0,
            "average_ticket": paid_totals["average_ticket"] or 0,
            "orders": queryset.count(),
            "orders_total": all_orders.count(),
            "orders_open": all_orders.filter(status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT]).count(),
            "orders_cancelled": all_orders.filter(status=Order.STATUS_CANCELLED).count(),
            "payments_total": approved_payments.aggregate(value=Sum("amount"))["value"] or 0,
            "payments_count": approved_payments.count(),
            "payments_refunded": payments.filter(status=Payment.STATUS_REFUNDED).aggregate(
                total=Sum("amount"), count=Count("id")
            ),
            "items_quantity": product_totals["quantity"] or 0,
            "items_total": product_totals["total"] or 0,
            "by_payment_method": list(by_payment),
            "by_restaurant": list(by_restaurant),
            "by_waiter": list(by_waiter),
            "by_product": list(by_product),
            "by_status": list(by_status),
            "by_order_type": list(by_order_type),
            "by_cancellation_reason": cancellation_reasons,
        }

        if export == "csv":
            return self._csv_response(data, date_from, date_to)

        return Response(self._section_response(data, request))

    def _section_response(self, data, request):
        section_keys = {
            "sales": (
                "by_payment_method", "by_restaurant", "by_waiter", "by_product",
                "by_status", "by_order_type", "by_cancellation_reason",
            ),
            "orders": ("by_status", "by_order_type", "by_cancellation_reason"),
            "products": ("by_product",),
            "payments": ("by_payment_method",),
            "waiters": ("by_waiter",),
            "restaurants": ("by_restaurant",),
        }
        keys = section_keys.get(self.report_section, section_keys["sales"])
        page = self._positive_int(request.query_params.get("page"), 1)
        page_size = min(self._positive_int(request.query_params.get("page_size"), 10), 100)
        pagination = {}

        for key in section_keys["sales"]:
            if key not in keys:
                data.pop(key, None)

        for key in keys:
            rows = data.get(key, [])
            count = len(rows)
            start = (page - 1) * page_size
            data[key] = rows[start:start + page_size]
            pagination[key] = {
                "page": page,
                "page_size": page_size,
                "count": count,
                "pages": max(1, (count + page_size - 1) // page_size),
            }

        data["pagination"] = pagination
        data["filters"] = {
            "date_from": request.query_params.get("date_from"),
            "date_to": request.query_params.get("date_to"),
            "restaurant": request.query_params.get("restaurant"),
            "category": request.query_params.get("category"),
            "sector": request.query_params.get("sector"),
            "product_type": request.query_params.get("product_type"),
            "production_sector": request.query_params.get("production_sector"),
        }
        return data

    @staticmethod
    def _positive_int(value, default):
        try:
            parsed = int(value)
            return parsed if parsed > 0 else default
        except (TypeError, ValueError):
            return default

    def _csv_response(self, data, date_from, date_to):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        filename = f"sales_{date_from or 'all'}_{date_to or 'all'}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)

        writer.writerow(["StarChef — Sales Report"])
        writer.writerow([f"Period: {date_from or 'all'} to {date_to or 'all'}"])
        writer.writerow([f"Total: {data['total']}", f"Orders: {data['orders']}"])
        writer.writerow([])

        writer.writerow(["By Payment Method"])
        writer.writerow(["Method", "Total", "Transactions"])
        for row in data["by_payment_method"]:
            writer.writerow([row.get("payment_method__name") or "—", row["total"], row["count"]])
        writer.writerow([])

        writer.writerow(["By Restaurant"])
        writer.writerow(["Restaurant", "Total", "Orders"])
        for row in data["by_restaurant"]:
            writer.writerow([row["restaurant__trade_name"] or "—", row["total"], row["count"]])
        writer.writerow([])

        writer.writerow(["By Waiter"])
        writer.writerow(["Name", "Username", "Total", "Orders"])
        for row in data["by_waiter"]:
            full_name = f"{row['responsible_user__first_name']} {row['responsible_user__last_name']}".strip()
            writer.writerow([full_name or "—", row["responsible_user__username"] or "—", row["total"], row["count"]])
        writer.writerow([])

        writer.writerow(["By Product"])
        writer.writerow(["Product", "Quantity", "Total"])
        for row in data["by_product"]:
            writer.writerow([row["product__name"], row["quantity"], row["total"]])

        return response


class OrdersReportView(SalesReportView):
    report_section = "orders"


class ProductsReportView(SalesReportView):
    report_section = "products"


class PaymentsReportView(SalesReportView):
    report_section = "payments"


class WaitersReportView(SalesReportView):
    report_section = "waiters"


class RestaurantsReportView(SalesReportView):
    report_section = "restaurants"
