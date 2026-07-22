from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer

from apps.restaurants.models import Branch, Command, DeliveryZone, Deliveryman, Restaurant, Table, TableSector


class RestaurantSerializer(TenantModelSerializer):
    # CNPJ opcional (não obrigatório). Vazio vira null para não colidir no unique.
    cnpj = serializers.CharField(max_length=18, required=False, allow_null=True, allow_blank=True, default=None)

    class Meta:
        model = Restaurant
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def validate_cnpj(self, value):
        return value or None


class BranchSerializer(TenantModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True)

    class Meta:
        model = Branch
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class TableSectorSerializer(TenantModelSerializer):
    class Meta:
        model = TableSector
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class TableSerializer(TenantModelSerializer):
    sector_name = serializers.CharField(source="sector.name", read_only=True)

    class Meta:
        model = Table
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class CommandSerializer(TenantModelSerializer):
    class Meta:
        model = Command
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class DeliveryZoneSerializer(TenantModelSerializer):
    class Meta:
        model = DeliveryZone
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class DeliverymanSerializer(TenantModelSerializer):
    class Meta:
        model = Deliveryman
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

