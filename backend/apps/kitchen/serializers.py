from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer

from .models import KdsColumn, KdsStation
from .rule_schema import DEFAULT_STATION_RULES, validate_station_rules


class KdsColumnSerializer(TenantModelSerializer):
    station_name = serializers.CharField(source="station.name", read_only=True)
    # Rótulo composto "Estação · Coluna" — usado no multiselect do SLA.
    label = serializers.SerializerMethodField()

    class Meta:
        model = KdsColumn
        fields = [
            "id", "station", "station_name", "label", "name", "position", "color",
            "is_entry", "is_done", "blocks_cancel", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_label(self, obj):
        return f"{obj.station.name} · {obj.name}"


class KdsStationSerializer(TenantModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    # Colunas do quadro (somente leitura aqui; criadas/editadas via /kitchen/columns/).
    columns = KdsColumnSerializer(many=True, read_only=True)

    class Meta:
        model = KdsStation
        fields = [
            "id", "name", "restaurant", "restaurant_name", "branch", "branch_name",
            "sla_minutes", "sectors", "rules", "is_active", "columns",
        ]
        # restaurant/branch precisam ser graváveis: a estação é vinculada ao
        # restaurante escolhido no formulário (antes eram read-only e o valor
        # selecionado era ignorado, causando erro de "restaurante obrigatório").
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_rules(self, value):
        return validate_station_rules(value, self.instance)

    def create(self, validated_data):
        if "rules" not in validated_data:
            validated_data["rules"] = [dict(rule) for rule in DEFAULT_STATION_RULES]
        return super().create(validated_data)
