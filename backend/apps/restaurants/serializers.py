from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer

from apps.restaurants.models import Branch, Command, Restaurant, Table, TableSector


class RestaurantSerializer(TenantModelSerializer):
    class Meta:
        model = Restaurant
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class BranchSerializer(TenantModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True)

    class Meta:
        model = Branch
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class TableSectorSerializer(TenantModelSerializer):
    class Meta:
        model = TableSector
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class TableSerializer(TenantModelSerializer):
    sector_name = serializers.CharField(source="sector.name", read_only=True)

    class Meta:
        model = Table
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class CommandSerializer(TenantModelSerializer):
    class Meta:
        model = Command
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]

