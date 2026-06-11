from rest_framework import viewsets

from apps.core.mixins import AuditCreateUpdateMixin, TenantQuerySetMixin
from apps.restaurants.models import Branch, Restaurant, Table, TableSector
from apps.restaurants.serializers import BranchSerializer, RestaurantSerializer, TableSectorSerializer, TableSerializer


class RestaurantViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = RestaurantSerializer
    queryset = Restaurant.all_objects.all()
    search_fields = ["trade_name", "legal_name", "cnpj"]
    ordering_fields = ["trade_name", "created_at"]


class BranchViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = BranchSerializer
    queryset = Branch.objects.select_related("restaurant").all()
    filterset_fields = ["restaurant", "is_active"]
    search_fields = ["name", "cnpj"]
    ordering_fields = ["name", "created_at"]


class TableSectorViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = TableSectorSerializer
    queryset = TableSector.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["restaurant", "branch", "is_active"]
    search_fields = ["name"]


class TableViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = TableSerializer
    queryset = Table.objects.select_related("restaurant", "branch", "sector").all()
    filterset_fields = ["restaurant", "branch", "sector", "status", "is_active"]
    search_fields = ["number"]
    ordering_fields = ["number", "status", "updated_at"]
