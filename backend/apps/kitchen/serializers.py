from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer

from .models import KdsStation


class KdsStationSerializer(TenantModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = KdsStation
        fields = ["id", "name", "restaurant", "restaurant_name", "branch", "branch_name", "sla_minutes", "sectors", "is_active"]
        read_only_fields = ["id", "restaurant", "branch", "created_at", "updated_at"]
