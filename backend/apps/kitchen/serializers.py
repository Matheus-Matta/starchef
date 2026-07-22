from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer

from .models import KdsStation


class KdsStationSerializer(TenantModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = KdsStation
        fields = ["id", "name", "restaurant", "restaurant_name", "branch", "branch_name", "sla_minutes", "sectors", "is_active"]
        # restaurant/branch precisam ser graváveis: a estação é vinculada ao
        # restaurante escolhido no formulário (antes eram read-only e o valor
        # selecionado era ignorado, causando erro de "restaurante obrigatório").
        read_only_fields = ["id", "created_at", "updated_at"]
