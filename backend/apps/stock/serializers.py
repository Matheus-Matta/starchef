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
    Supplier,
)


class StockLocationSerializer(TenantModelSerializer):
    # O armazem e quem localiza o estoque, entao a tela precisa dizer de
    # QUAL unidade ele e — a lista mistura os armazens de toda a conta.
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True, default="")

    class Meta:
        model = StockLocation
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class SupplierSerializer(TenantModelSerializer):
    class Meta:
        model = Supplier
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def validate_name(self, value):
        name = str(value or "").strip()
        if not name:
            raise serializers.ValidationError("Informe o nome do fornecedor.")
        account = getattr(self.context.get("request"), "account", None)
        duplicates = Supplier.all_objects.filter(name__iexact=name, deleted_at__isnull=True)
        if account is not None:
            duplicates = duplicates.filter(account=account)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("Ja existe um fornecedor com este nome.")
        return name


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
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default="")
    lots = StockLotSerializer(many=True, read_only=True)

    class Meta:
        model = StockEntryItem
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "entry", "base_quantity", "total_cost"]
        extra_kwargs = {
            "ingredient": {
                "error_messages": {
                    "null": "Selecione o insumo recebido.",
                    "required": "Selecione o insumo recebido.",
                    "does_not_exist": "O insumo selecionado nao foi encontrado neste restaurante.",
                }
            },
            "package_quantity": {
                "error_messages": {
                    "null": "Informe quantas embalagens foram recebidas.",
                    "invalid": "Informe uma quantidade de embalagens valida.",
                }
            },
            "content_per_package": {
                "error_messages": {
                    "null": "Informe quanto ha em cada embalagem, por exemplo: 1 para um pacote de 1 kg.",
                    "invalid": "Informe um conteudo por embalagem valido.",
                }
            },
            "manufactured_at": {
                "error_messages": {"invalid": "Informe uma data de fabricacao valida."}
            },
            "expires_at": {
                "error_messages": {"invalid": "Informe uma data de validade valida."}
            },
        }

    def validate(self, attrs):
        ingredient = attrs.get("ingredient") or getattr(self.instance, "ingredient", None)
        if ingredient is not None:
            if not attrs.get("content_unit"):
                attrs["content_unit"] = ingredient.unit
            if attrs.get("supplier") is None:
                attrs["supplier"] = ingredient.supplier

        errors = {}
        package_quantity = attrs.get("package_quantity", getattr(self.instance, "package_quantity", 1))
        content_per_package = attrs.get(
            "content_per_package", getattr(self.instance, "content_per_package", 1)
        )
        if package_quantity is None or package_quantity <= 0:
            errors["package_quantity"] = "Informe uma quantidade de embalagens maior que zero."
        if content_per_package is None or content_per_package <= 0:
            errors["content_per_package"] = (
                "Informe quanto ha em cada embalagem com um valor maior que zero. "
                "Exemplo: para um pacote de 1 kg, informe 1 e selecione kg."
            )

        manufactured_at = attrs.get("manufactured_at", getattr(self.instance, "manufactured_at", None))
        expires_at = attrs.get("expires_at", getattr(self.instance, "expires_at", None))
        if manufactured_at and expires_at and manufactured_at > expires_at:
            errors["expires_at"] = "A validade deve ser posterior a data de fabricacao."
        label_count = attrs.get("label_count", getattr(self.instance, "label_count", 1))
        if label_count is not None and not 1 <= label_count <= 99:
            errors["label_count"] = "Informe uma quantidade de etiquetas entre 1 e 99."
        if errors:
            raise serializers.ValidationError(errors)
        return super().validate(attrs)


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
        # O restaurante NAO e perguntado: ele sai do armazem escolhido.
        # Perguntar os dois abria espaco para a entrada dizer um
        # restaurante e o estoque cair em outro.
        extra_kwargs = {
            "restaurant": {"required": False, "allow_null": True},
            "location": {
                "error_messages": {
                    "null": "Selecione o armazem que recebera os produtos.",
                    "required": "Selecione o armazem que recebera os produtos.",
                    "does_not_exist": "O armazem selecionado nao foi encontrado neste restaurante.",
                }
            },
            "effective_date": {
                "error_messages": {
                    "null": "Informe a data da entrada.",
                    "required": "Informe a data da entrada.",
                    "invalid": "Informe uma data de entrada valida.",
                }
            },
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        location = attrs.get("location") or getattr(self.instance, "location", None)
        items = attrs.get("items")
        errors = {}

        # O armazem e quem localiza o estoque; o restaurante da entrada e
        # consequencia dele. Assim o saldo de uma unidade e sempre a soma
        # dos armazens dela, sem depender de dois campos concordarem.
        #
        # O insumo nao entra nesta conferencia: ele e cadastro da CONTA e
        # vale para qualquer armazem (ver `menu.Ingredient`).
        if location is not None:
            attrs["restaurant"] = location.restaurant
            attrs["branch"] = location.branch

        effective_date = attrs.get("effective_date", getattr(self.instance, "effective_date", None))
        if effective_date is not None and items is not None:
            item_errors = errors.get("items", [{} for _ in items])
            for index, row in enumerate(items):
                expires_at = row.get("expires_at")
                if expires_at and expires_at < effective_date:
                    item_errors[index]["expires_at"] = (
                        "A validade nao pode ser anterior a data da entrada."
                    )
            if any(item_errors):
                errors["items"] = item_errors

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def _write_items(self, entry, items_data):
        entry.items.all().delete()
        for row in items_data:
            for inherited_field in (
                "entry", "account", "restaurant", "branch", "created_by", "updated_by"
            ):
                row.pop(inherited_field, None)
            StockEntryItem.objects.create(
                entry=entry,
                account=entry.account,
                restaurant=entry.restaurant,
                branch=entry.branch,
                created_by=entry.updated_by,
                updated_by=entry.updated_by,
                **row,
            )
        supplier_names = list(
            entry.items.filter(supplier__isnull=False)
            .order_by("supplier__name")
            .values_list("supplier__name", flat=True)
            .distinct()
        )
        if supplier_names:
            summary = ", ".join(supplier_names)
            entry.supplier = summary if len(summary) <= 160 else "Varios fornecedores"
            entry.save(update_fields=["supplier", "updated_at"])

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
            for inherited_field in (
                "exit", "account", "restaurant", "branch", "created_by", "updated_by"
            ):
                row.pop(inherited_field, None)
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
