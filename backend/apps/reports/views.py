from django.db.models import Avg, Count, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

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
        profile = getattr(user, "profile", None)
        if not profile:
            return {"account_id": None}
        if profile.restaurant_id:
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

        top_products = (
            self.tenant_manager(OrderItem)
            .filter(order__opened_at__date=today, order__payment_status=Order.PAYMENT_PAID, **filters)
            .values("product__name")
            .annotate(quantity=Sum("quantity"), total=Sum("total_price"))
            .order_by("-quantity")[:10]
        )

        low_stock = (
            self.tenant_manager(StockMovement)
            .filter(**filters)
            .values("ingredient__name")
            .annotate(balance=Sum("quantity"))
            .filter(balance__lte=0)
            .order_by("balance")[:10]
        )

        data = {
            "total_sold_today": paid_orders.aggregate(value=Sum("total"))["value"] or 0,
            "orders_count": orders.count(),
            "open_orders": orders.exclude(status__in=[Order.STATUS_PAID, Order.STATUS_CANCELLED]).count(),
            "paid_orders": paid_orders.count(),
            "cancelled_orders": orders.filter(status=Order.STATUS_CANCELLED).count(),
            "average_ticket": paid_orders.aggregate(value=Avg("total"))["value"] or 0,
            "top_products": list(top_products),
            "low_stock": list(low_stock),
        }
        return Response(data)


class SalesReportView(TenantReportMixin, APIView):
    def get(self, request):
        filters = self.tenant_filter()
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
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
        return Response(
            {
                "total": queryset.aggregate(value=Sum("total"))["value"] or 0,
                "orders": queryset.count(),
                "by_payment_method": list(by_payment),
                "by_branch": list(by_branch),
            }
        )
