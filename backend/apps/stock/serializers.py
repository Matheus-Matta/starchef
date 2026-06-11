from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer

from apps.stock.models import StockLocation, StockMovement


class StockLocationSerializer(TenantModelSerializer):
    class Meta:
        model = StockLocation
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class StockMovementSerializer(TenantModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = StockMovement
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by", "total_cost"]

