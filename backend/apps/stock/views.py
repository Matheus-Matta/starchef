from rest_framework import viewsets

from apps.core.mixins import AuditCreateUpdateMixin, TenantQuerySetMixin
from apps.stock.models import StockLocation, StockMovement
from apps.stock.serializers import StockLocationSerializer, StockMovementSerializer


class StockLocationViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = StockLocationSerializer
    queryset = StockLocation.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["restaurant", "branch", "is_active"]
    search_fields = ["name"]


class StockMovementViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = StockMovementSerializer
    queryset = StockMovement.objects.select_related("restaurant", "branch", "ingredient", "location", "operator").all()
    filterset_fields = ["restaurant", "branch", "ingredient", "location", "movement_type"]
    ordering_fields = ["created_at", "quantity", "total_cost"]

