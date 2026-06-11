from django.core.exceptions import ValidationError
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins import TenantQuerySetMixin
from apps.orders.models import Order, OrderItem
from apps.orders.serializers import OrderItemSerializer, OrderSerializer
from apps.orders.services import update_order_item_status


class KitchenOrderViewSet(TenantQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = OrderSerializer
    queryset = (
        Order.objects.select_related("restaurant", "branch", "table", "command", "customer")
        .prefetch_related("items__product", "items__addons")
        .exclude(status__in=[Order.STATUS_PAID, Order.STATUS_CANCELLED, Order.STATUS_REFUNDED])
    )
    filterset_fields = ["restaurant", "branch", "status", "order_type", "items__production_sector"]
    ordering_fields = ["opened_at", "sequence"]


class KitchenItemViewSet(TenantQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = OrderItemSerializer
    queryset = OrderItem.objects.select_related("restaurant", "branch", "order", "product").prefetch_related("addons").all()
    filterset_fields = ["restaurant", "branch", "production_sector", "status"]
    ordering_fields = ["launched_at", "ready_at"]

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        try:
            item = update_order_item_status(
                self.get_object(),
                request.data["status"],
                request.user,
                reason=request.data.get("reason", ""),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(item).data)
