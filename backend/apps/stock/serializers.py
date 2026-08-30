from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer

from apps.stock.models import (
    StockAllocation,
    StockEntry,
    StockEntryItem,
    StockExit,
    StockExitItem,
    StockLabelTemplate,
    StockLocation,
    StockLot,
    StockMovement,
    StockSettings,
)


class StockLocationSerializer(TenantModelSerializer):
    class Meta:
        model = StockLocation
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class StockSettingsSerializer(TenantModelSerializer):
    class Meta:
        model = StockSettings
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class StockLabelTemplateSerializer(TenantModelSerializer):
    class Meta:
        model = StockLabelTemplate
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def validate(self, attrs):
        attrs = super().validate(attrs)
        for field in ("width_mm", "height_mm"):
            value = attrs.get(field, getattr(self.instance, field, None))
            if value is not None and value <= 0:
                raise serializers.ValidationError({field: "Informe uma medida maior que zero."})
        return attrs


class StockMovementSerializer(TenantModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    lot_code = serializers.CharField(source="lot.code", read_only=True, default=None)

    class Meta:
        model = StockMovement
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "total_cost"]


class StockLotSerializer(TenantModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    ingredient_unit = serializers.CharField(source="ingredient.unit", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = StockLot
        fields = "__all__"
        # O codigo e a quantidade nunca sao editados pela API: o primeiro esta
        # impresso numa etiqueta colada na embalagem, e o segundo so muda por
        # movimento — editar aqui abriria um saldo sem rastro no livro.
        read_only_fields = [
            *AUDIT_READ_ONLY_FIELDS,
            "code",
            "quantity",
            "initial_quantity",
            "entry_item",
        ]


class StockEntryItemSerializer(TenantModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    ingredient_unit = serializers.CharField(source="ingredient.unit", read_only=True)
    lots = StockLotSerializer(many=True, read_only=True)

    class Meta:
        model = StockEntryItem
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "entry", "base_quantity", "total_cost"]


class StockEntrySerializer(TenantModelSerializer):
    """A entrada e suas linhas chegam juntas: o formulario e um documento so.

    Sem o aninhamento, a tela precisaria criar o cabecalho, depois cada linha,
    e lidar com a metade de uma entrada que ficou salva quando algo falhou no
    meio.
    """

    items = StockEntryItemSerializer(many=True, required=False)
    location_name = serializers.CharField(source="location.name", read_only=True)
    is_editable = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockEntry
        fields = "__all__"
        read_only_fields = [
            *AUDIT_READ_ONLY_FIELDS, "status", "posted_at", "posted_by", "cancelled_at", "cancelled_by"
        ]

    def _write_items(self, entry, items_data):
        entry.items.all().delete()
        for row in items_data:
            row.pop("entry", None)
            StockEntryItem.objects.create(
                entry=entry,
                account=entry.account,
                restaurant=entry.restaurant,
                branch=entry.branch,
                created_by=entry.updated_by,
                updated_by=entry.updated_by,
                **row,
            )

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        entry = super().create(validated_data)
        self._write_items(entry, items_data)
        return entry

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        if not instance.is_editable:
            raise serializers.ValidationError("Uma entrada confirmada ou cancelada nao pode ser alterada.")
        entry = super().update(instance, validated_data)
        if items_data is not None:
            self._write_items(entry, items_data)
        return entry


class StockAllocationSerializer(TenantModelSerializer):
    lot_code = serializers.CharField(source="lot.code", read_only=True)
    lot_expires_at = serializers.DateField(source="lot.expires_at", read_only=True)
    lot_entered_at = serializers.DateField(source="lot.entered_at", read_only=True)
    lot_available = serializers.DecimalField(
        source="lot.quantity", max_digits=14, decimal_places=3, read_only=True
    )
    ingredient_name = serializers.CharField(source="exit_item.ingredient.name", read_only=True)
    is_confirmed = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockAllocation
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "scanned_at", "scanned_by", "scanned_code"]


class StockExitItemSerializer(TenantModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    ingredient_unit = serializers.CharField(source="ingredient.unit", read_only=True)
    allocations = StockAllocationSerializer(many=True, read_only=True)

    class Meta:
        model = StockExitItem
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "exit", "fulfilled_quantity"]


class StockExitSerializer(TenantModelSerializer):
    items = StockExitItemSerializer(many=True, required=False)
    location_name = serializers.CharField(source="location.name", read_only=True)
    is_editable = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockExit
        fields = "__all__"
        read_only_fields = [
            *AUDIT_READ_ONLY_FIELDS,
            "status",
            "picking_strategy",
            "posted_at",
            "posted_by",
            "cancelled_at",
            "cancelled_by",
        ]

    def validate_reason(self, value):
        if not str(value or "").strip():
            raise serializers.ValidationError("O motivo da saida e obrigatorio.")
        return value

    def _write_items(self, exit_document, items_data):
        exit_document.items.all().delete()
        for row in items_data:
            row.pop("exit", None)
            StockExitItem.objects.create(
                exit=exit_document,
                account=exit_document.account,
                restaurant=exit_document.restaurant,
                branch=exit_document.branch,
                created_by=exit_document.updated_by,
                updated_by=exit_document.updated_by,
                **row,
            )

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        exit_document = super().create(validated_data)
        self._write_items(exit_document, items_data)
        return exit_document

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        if not instance.is_editable:
            raise serializers.ValidationError("Uma saida confirmada ou cancelada nao pode ser alterada.")
        exit_document = super().update(instance, validated_data)
        if items_data is not None:
            self._write_items(exit_document, items_data)
        return exit_document
