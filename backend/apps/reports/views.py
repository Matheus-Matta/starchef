import csv
from calendar import monthrange
from datetime import timedelta

from django.db.models import Avg, Count, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import is_tenant_admin
from apps.menu.models import Ingredient
from apps.orders.models import Order, OrderItem
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
    def get(self, request):
        filters = self.tenant_filter()
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        export = request.query_params.get("export")

        queryset = self.tenant_manager(Order).filter(payment_status=Order.PAYMENT_PAID, **filters)
        if date_from:
            queryset = queryset.filter(opened_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(opened_at__date__lte=date_to)

        by_payment = (
            queryset.values("payments__payment_method__name")
            .annotate(total=Sum("payments__amount"), count=Count("payments"))
            .order_by("-total")
        )
        by_branch = queryset.values("branch__name").annotate(total=Sum("total"), count=Count("id")).order_by("-total")
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
        by_product = (
            self.tenant_manager(OrderItem)
            .filter(order__payment_status=Order.PAYMENT_PAID, **filters)
            .filter(
                **({} if not date_from else {"order__opened_at__date__gte": date_from}),
                **({} if not date_to else {"order__opened_at__date__lte": date_to}),
            )
            .values("product__id", "product__name", "product__sale_price")
            .annotate(quantity=Sum("quantity"), total=Sum("total_price"))
            .order_by("-total")
        )

        data = {
            "total": queryset.aggregate(value=Sum("total"))["value"] or 0,
            "orders": queryset.count(),
            "by_payment_method": list(by_payment),
            "by_branch": list(by_branch),
            "by_waiter": list(by_waiter),
            "by_product": list(by_product),
        }

        if export == "csv":
            return self._csv_response(data, date_from, date_to)

        return Response(data)

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
            writer.writerow([row.get("payments__payment_method__name") or "—", row["total"], row["count"]])
        writer.writerow([])

        writer.writerow(["By Branch"])
        writer.writerow(["Branch", "Total", "Orders"])
        for row in data["by_branch"]:
            writer.writerow([row["branch__name"], row["total"], row["count"]])
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
