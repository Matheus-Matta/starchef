from django.core.exceptions import ValidationError
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins import AuditCreateUpdateMixin, TenantQuerySetMixin
from apps.orders.models import Order, OrderItem
from apps.orders.serializers import OrderItemSerializer, OrderSerializer
from apps.orders.services import update_order_item_status

from .models import KdsStation
from .serializers import KdsStationSerializer

# Orders active in the kitchen — exclude definitively closed/cancelled
_INACTIVE_ORDER_STATUSES = [Order.STATUS_CANCELLED, Order.STATUS_REFUNDED]
_ACTIVE_PRODUCTION_STATUSES = [
    Order.PROD_SENT,
    Order.PROD_PREPARING,
    Order.PROD_PARTIALLY_READY,
    Order.PROD_READY,
]

_ACTIVE_ITEM_STATUSES = [OrderItem.STATUS_SENT, OrderItem.STATUS_PREPARING, OrderItem.STATUS_READY]


class KitchenOrderViewSet(TenantQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = OrderSerializer
    queryset = (
        Order.objects.select_related("restaurant", "branch", "table", "command", "customer")
        .prefetch_related("items__product", "items__addons", "items__batch")
        .exclude(status__in=_INACTIVE_ORDER_STATUSES)
        .filter(production_status__in=_ACTIVE_PRODUCTION_STATUSES)
    )
    filterset_fields = ["restaurant", "branch", "status", "production_status", "order_type", "items__production_sector"]
    ordering_fields = ["opened_at", "sequence"]


class KitchenItemViewSet(TenantQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = OrderItemSerializer
    queryset = (
        OrderItem.objects.select_related("restaurant", "branch", "order__table", "order__command", "product", "batch")
        .prefetch_related("addons")
        .all()
    )
    filterset_fields = ["restaurant", "branch", "production_sector", "status"]
    ordering_fields = ["launched_at", "ready_at", "sent_to_kitchen_at"]

    def get_queryset(self):
        return super().get_queryset().filter(status__in=_ACTIVE_ITEM_STATUSES)

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


class KdsStationViewSet(TenantQuerySetMixin, AuditCreateUpdateMixin, viewsets.ModelViewSet):
    serializer_class = KdsStationSerializer
    queryset = KdsStation.objects.all()
    filterset_fields = ["restaurant", "branch", "is_active"]
