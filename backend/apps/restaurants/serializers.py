from django.contrib.auth.hashers import PBKDF2PasswordHasher
from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer

from apps.restaurants.models import (
    Branch,
    Command,
    CommandMovementLog,
    DeliveryZone,
    Deliveryman,
    Restaurant,
    Table,
    TableSector,
)


class RestaurantSerializer(TenantModelSerializer):
    # CNPJ opcional (não obrigatório). Vazio vira null para não colidir no unique.
    cnpj = serializers.CharField(max_length=18, required=False, allow_null=True, allow_blank=True, default=None)
    # Senha de ações do caixa: entra em texto (write-only), sai só como booleano.
    cash_action_password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        style={"input_type": "password"},
        help_text="Senha para autorizar ações do caixa. Enviada em texto; armazenada com hash.",
    )
    has_cash_action_password = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def get_has_cash_action_password(self, obj):
        return bool(obj.cash_action_password)

    def validate_cnpj(self, value):
        return value or None

    def _hash_cash_password(self, validated_data):
        # Só (re)define quando um valor não-vazio é enviado — senão mantém o atual.
        raw = validated_data.pop("cash_action_password", None)
        if raw:
            hasher = PBKDF2PasswordHasher()
            validated_data["cash_action_password"] = hasher.encode(
                raw,
                hasher.salt(),
            )
        return validated_data

    def create(self, validated_data):
        return super().create(self._hash_cash_password(validated_data))

    def update(self, instance, validated_data):
        return super().update(instance, self._hash_cash_password(validated_data))

    def validate_default_service_fee_percent(self, value):
        if value < 0:
            raise serializers.ValidationError("O percentual da taxa de serviço não pode ser negativo.")
        return value


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


class CommandSerializer(TenantModelSerializer):
    # Numero e opcional na escrita: quando omitido, o model atribui o proximo
    # sequencial do restaurante. `code` idem (derivado do numero).
    number = serializers.IntegerField(required=False, min_value=1)
    code = serializers.CharField(required=False, allow_blank=True, max_length=40)
    current_table_number = serializers.CharField(source="current_table.number", read_only=True, default=None)

    class Meta:
        model = Command
        fields = "__all__"
        # status, current_order_id e current_table sao geridos pelo ciclo de vida
        # (pedido/pagamento e endpoints de mesa), nunca definidos direto pelo CRUD cliente.
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "status", "current_order_id", "current_table"]

    def validate(self, attrs):
        if (
            attrs.get("is_active") is False
            and self.instance is not None
            and (self.instance.current_order_id or self.instance.current_table_id)
        ):
            raise serializers.ValidationError({"is_active": "Desvincule e encerre a comanda antes de desativá-la."})
        return attrs


class TableSerializer(TenantModelSerializer):
    sector_name = serializers.CharField(source="sector.name", read_only=True)
    code = serializers.CharField(required=False, allow_blank=True, max_length=40, default="")
    active_commands = CommandSerializer(many=True, read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Table
        fields = "__all__"
        # Estado e vinculo com pedido pertencem ao fluxo transacional, nao ao CRUD.
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "status", "current_order_id"]

    def get_status(self, obj):
        # O vínculo é a fonte de verdade operacional. Bases antigas podem ter
        # mantido `status=free`; a API nunca deve desenhar essa mesa como livre.
        commands = getattr(obj, "_prefetched_objects_cache", {}).get("active_commands")
        occupied = bool(commands) if commands is not None else obj.active_commands.exists()
        return Table.STATUS_OCCUPIED if occupied else obj.status


class CommandMovementLogSerializer(TenantModelSerializer):
    class Meta:
        model = CommandMovementLog
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
