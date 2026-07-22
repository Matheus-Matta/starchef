from apps.core.modules import MODULE_ENTREGA
from apps.core.viewsets import BaseTenantViewSet
from apps.restaurants.models import Branch, DeliveryZone, Deliveryman, Restaurant, Table, TableSector
from apps.restaurants.serializers import (
    BranchSerializer,
    DeliveryZoneSerializer,
    DeliverymanSerializer,
    RestaurantSerializer,
    TableSectorSerializer,
    TableSerializer,
)


class RestaurantViewSet(BaseTenantViewSet):
    serializer_class = RestaurantSerializer
    queryset = Restaurant.all_objects.all()
    search_fields = ["trade_name", "legal_name", "cnpj"]
    ordering_fields = ["trade_name", "created_at"]


class BranchViewSet(BaseTenantViewSet):
    serializer_class = BranchSerializer
    queryset = Branch.objects.select_related("restaurant").all()
    filterset_fields = ["restaurant", "is_active"]
    search_fields = ["name", "cnpj"]
    ordering_fields = ["name", "created_at"]


class TableSectorViewSet(BaseTenantViewSet):
    serializer_class = TableSectorSerializer
    queryset = TableSector.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["restaurant", "branch", "is_active"]
    search_fields = ["name"]


class TableViewSet(BaseTenantViewSet):
    serializer_class = TableSerializer
    queryset = Table.objects.select_related("restaurant", "branch", "sector").all()
    filterset_fields = ["restaurant", "branch", "sector", "status", "is_active"]
    search_fields = ["number"]
    ordering_fields = ["number", "status", "updated_at"]


class DeliveryZoneViewSet(BaseTenantViewSet):
    required_module = MODULE_ENTREGA  # gestao logistica de delivery
    serializer_class = DeliveryZoneSerializer
    queryset = DeliveryZone.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["restaurant", "branch", "is_active"]
    search_fields = ["name"]
    ordering_fields = ["min_radius_km", "delivery_fee"]


class DeliverymanViewSet(BaseTenantViewSet):
    required_module = MODULE_ENTREGA  # gestao logistica de delivery
    serializer_class = DeliverymanSerializer
    queryset = Deliveryman.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["restaurant", "branch", "vehicle_type", "is_active"]
    search_fields = ["name", "phone"]
