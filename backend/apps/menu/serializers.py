from django.utils.text import slugify
from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer
from apps.images.product_serializers import ProductImagesMixin, VariationImageMixin
from apps.images.serializers import LogoImageMixin

from apps.menu.barcodes import GTIN_LENGTHS, is_valid_gtin, normalize_barcode
from apps.menu.units import IncompatibleUnitError, convert
from apps.menu.models import (
    Ingredient,
    Menu,
    MenuItem,
    Product,
    ProductAddon,
    ProductCategory,
    ProductVariation,
    Recipe,
    RecipeItem,
)


class ProductCategorySerializer(LogoImageMixin, TenantModelSerializer):
    # A UniqueConstraint (branch, name, parent) faz o DRF gerar um
    # UniqueTogetherValidator que, por padrão, exigiria `parent` no payload —
    # a causa do erro silencioso no cadastro de categoria (STC-023). Declarar o
    # campo com default=None torna a categoria raiz (sem pai) válida.
    parent = serializers.PrimaryKeyRelatedField(
        queryset=ProductCategory.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )

    class Meta:
        model = ProductCategory
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Unicidade de nome por filial/pai. O DB trata parent=NULL como distinto
        # (permitiria categorias-raiz duplicadas), então validamos aqui para dar
        # um erro claro no campo `name` (STC-023) em vez de duplicar em silêncio.
        name = attrs.get("name", getattr(self.instance, "name", None))
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        branch = attrs.get("branch", getattr(self.instance, "branch", None))
        if name is None:
            return attrs

        siblings = ProductCategory.objects.filter(name__iexact=name, parent=parent)
        if branch is not None:
            siblings = siblings.filter(branch=branch)
        if self.instance is not None:
            siblings = siblings.exclude(pk=self.instance.pk)
        if siblings.exists():
            raise serializers.ValidationError({"name": "Já existe uma categoria com este nome."})
        return attrs


class ProductVariationSerializer(VariationImageMixin, TenantModelSerializer):
    class Meta:
        model = ProductVariation
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS
        # Diferenca de preco da variacao: "sem queijo" custa menos.
        signed_fields = ["price_delta"]


def _validate_consumption(serializer, attrs, *, ingredient_field, quantity_field, unit_field):
    """Coerencia entre insumo, quantidade e unidade de um vinculo de consumo."""
    def current(name):
        if name in attrs:
            return attrs[name]
        return getattr(serializer.instance, name, None)

    ingredient = current(ingredient_field)
    quantity = current(quantity_field) or 0
    unit = current(unit_field) or ""

    if ingredient is None:
        if quantity:
            raise serializers.ValidationError(
                {ingredient_field: "Informe o insumo consumido ou zere a quantidade de consumo."}
            )
        return attrs

    if quantity <= 0:
        raise serializers.ValidationError(
            {quantity_field: "Informe quanto do insumo cada unidade vendida consome."}
        )

    if unit and unit != ingredient.unit:
        try:
            convert(quantity, unit, ingredient.unit)
        except IncompatibleUnitError:
            raise serializers.ValidationError(
                {unit_field: f"Nao e possivel converter {unit} para {ingredient.unit}, a unidade do insumo."}
            ) from None
    return attrs


class ProductAddonSerializer(TenantModelSerializer):
    class Meta:
        model = ProductAddon
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def validate(self, attrs):
        """O consumo declarado precisa fechar com a unidade do insumo.

        A checagem vive aqui, e nao so na baixa: no momento da venda uma
        unidade incoerente e apenas ignorada (o pedido ja foi pago e travar o
        fechamento deixaria o operador sem saida), entao o erro passaria em
        silencio e so apareceria como falta no inventario.
        """
        return _validate_consumption(
            self, attrs,
            ingredient_field="ingredient",
            quantity_field="consumption_quantity",
            unit_field="consumption_unit",
        )


class RecipeItemSerializer(TenantModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)

    class Meta:
        model = RecipeItem
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def validate_quantity(self, value):
        # Quantidade de ingrediente deve ser maior que zero (STC-034).
        if value is None or value <= 0:
            raise serializers.ValidationError("A quantidade deve ser maior que zero.")
        return value


class RecipeSerializer(TenantModelSerializer):
    items = RecipeItemSerializer(many=True, read_only=True)

    class Meta:
        model = Recipe
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "total_cost"]


class ProductSerializer(ProductImagesMixin, TenantModelSerializer):
    category_name = serializers.SerializerMethodField()
    sector_name = serializers.CharField(source="sector.name", read_only=True, default=None)
    current_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    variations = ProductVariationSerializer(many=True, read_only=True)
    recipe = RecipeSerializer(read_only=True)
    # Adicionais vinculados a este produto (gerenciados na edição do produto).
    addons = serializers.SerializerMethodField()
    restaurant_names = serializers.SerializerMethodField()

    def get_addons(self, obj):
        return [
            {"id": addon.id, "name": addon.name, "price": addon.price, "is_active": addon.is_active}
            for addon in obj.addons.all()
        ]

    def get_restaurant_names(self, obj):
        return [restaurant.trade_name for restaurant in obj.restaurants.all()]

    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS
        # `margin_percent` e assinado: vender abaixo do custo e uma decisao
        # possivel, e a margem negativa e o retrato dela.
        signed_fields = ["margin_percent"]

    def get_category_name(self, obj):
        return obj.category.name if obj.category_id else "Sem categoria"

    def validate_sector(self, value):
        if value and self.instance and value.branch_id != self.instance.branch_id:
            raise serializers.ValidationError("O setor deve pertencer à mesma filial do produto.")
        return value

    def validate_ean(self, value):
        """Normaliza e recusa duplicidade e dígito verificador errado.

        O erro precisa aparecer AQUI, no cadastro. Um código repetido só se
        manifestaria na frente do cliente, com o PDV tendo de escolher entre
        dois produtos sem ter como saber qual; e um dígito verificador errado
        vira um produto que o leitor nunca encontra.
        """
        raw = str(value or "").strip()
        if not raw:
            return ""
        digits = normalize_barcode(raw)
        if not digits:
            raise serializers.ValidationError("O código de barras deve conter apenas dígitos.")
        if len(digits) > 32:
            raise serializers.ValidationError("Código de barras longo demais (máximo 32 dígitos).")
        if len(digits) in GTIN_LENGTHS and not is_valid_gtin(digits):
            raise serializers.ValidationError(
                f"Dígito verificador inválido para um código de {len(digits)} dígitos. "
                "Confira a etiqueta — um código errado aqui é um produto que o leitor nunca acha."
            )

        account = getattr(self.context.get("request"), "account", None)
        duplicates = Product.all_objects.filter(ean=digits, deleted_at__isnull=True)
        if account is not None:
            duplicates = duplicates.filter(account=account)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        conflict = duplicates.first()
        if conflict is not None:
            raise serializers.ValidationError(
                f"O código {digits} já está cadastrado em \"{conflict.name}\". "
                "Dois produtos com o mesmo código deixariam o PDV escolher um deles em silêncio."
            )
        return digits

    def validate_restaurants(self, value):
        account = getattr(self.context.get("request"), "account", None)
        if account and any(restaurant.account_id != account.id for restaurant in value):
            raise serializers.ValidationError("Selecione apenas restaurantes da mesma conta.")
        if not value:
            raise serializers.ValidationError("Selecione ao menos um restaurante.")
        return value

    def validate(self, attrs):
        # A validação tenant genérica exige que toda relação pertença ao
        # restaurante principal. `restaurants` é justamente a exceção: pode
        # conter várias unidades, desde que todas pertençam à mesma conta.
        selected = attrs.pop("restaurants", serializers.empty)
        attrs = super().validate(attrs)
        if selected is not serializers.empty:
            attrs["restaurants"] = selected
        # Vínculo direto (refrigerante em lata e afins): mesma coerência
        # exigida do adicional. Produto COM ficha técnica ignora este vínculo
        # na baixa — a ficha descreve a composição real —, mas um cadastro
        # incoerente continua sendo recusado aqui.
        return _validate_consumption(
            self, attrs,
            ingredient_field="stock_ingredient",
            quantity_field="stock_consumption_quantity",
            unit_field="stock_consumption_unit",
        )


class IngredientListSerializer(serializers.ListSerializer):
    def validate(self, attrs):
        seen = set()
        errors = {}
        for index, row in enumerate(attrs):
            normalized = str(row.get("name") or "").strip().casefold()
            if normalized in seen:
                errors[index] = {"name": "O nome do insumo esta repetido neste lote."}
            seen.add(normalized)
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class IngredientSerializer(TenantModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default="")

    class Meta:
        model = Ingredient
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS
        list_serializer_class = IngredientListSerializer

    def validate_minimum_stock(self, value):
        # Opcional, mas não pode ser negativo quando informado (STC-031).
        if value is not None and value < 0:
            raise serializers.ValidationError("O estoque mínimo não pode ser negativo.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # O insumo é da conta: não se prende a restaurante nem a filial, e
        # aceitar um vínculo aqui faria ele sumir da busca das outras
        # unidades (o recorte por tenant esconde o que é de outro).
        attrs["restaurant"] = None
        attrs["branch"] = None
        # Nome único na CONTA — erro claro no campo em vez de 500 por
        # violação de constraint (STC-033).
        name = attrs.get("name", getattr(self.instance, "name", None))
        if name is not None:
            siblings = Ingredient.objects.filter(name__iexact=name)
            if self.instance is not None:
                siblings = siblings.exclude(pk=self.instance.pk)
            if siblings.exists():
                raise serializers.ValidationError(
                    {"name": "Já existe um insumo com este nome nesta conta."}
                )
        return attrs


class MenuItemSerializer(TenantModelSerializer):
    """Uma entrada de menu. O tipo decide qual alvo e obrigatorio."""

    product_name = serializers.CharField(source="product.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    label = serializers.CharField(read_only=True)
    effective_price = serializers.SerializerMethodField()
    children_count = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def get_effective_price(self, obj):
        if not obj.product_id:
            return None
        return obj.override_price if obj.override_price is not None else obj.product.current_price

    def get_children_count(self, obj):
        return obj.children.count()

    # Qual campo cada tipo exige. Sem isso, um item de produto sem produto
    # entraria no banco e sumiria do site sem erro nenhum — o pior resultado
    # possivel, porque o restaurante ve o item salvo no cadastro.
    REQUIRED_BY_TYPE = {
        MenuItem.TYPE_PRODUCT: ("product", "Escolha o produto deste item."),
        MenuItem.TYPE_CATEGORY: ("category", "Escolha a categoria deste item."),
        MenuItem.TYPE_IMAGE: ("image", "Envie a imagem deste item."),
        MenuItem.TYPE_CUSTOM: ("url", "Informe o link deste item."),
    }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance

        def value_of(field):
            if field in attrs:
                return attrs[field]
            return getattr(instance, field, None)

        item_type = value_of("item_type") or MenuItem.TYPE_PRODUCT
        required_field, message = self.REQUIRED_BY_TYPE[item_type]
        if not value_of(required_field):
            raise serializers.ValidationError({required_field: message})

        menu = value_of("menu")
        parent = value_of("parent")
        if parent is not None:
            if instance is not None and parent.pk == instance.pk:
                raise serializers.ValidationError({"parent": "Um item nao pode ser pai de si mesmo."})
            if menu is not None and parent.menu_id != menu.id:
                raise serializers.ValidationError({"parent": "O item pai pertence a outro menu."})
            # Profundidade: o pai ja ocupa um nivel, entao o filho fica um
            # abaixo. Tres niveis e o teto (ver `MenuItem.MAX_DEPTH`).
            if parent.depth >= MenuItem.MAX_DEPTH:
                raise serializers.ValidationError(
                    {"parent": f"O menu aceita no maximo {MenuItem.MAX_DEPTH} niveis."}
                )
            if instance is not None and _is_descendant(parent, instance):
                raise serializers.ValidationError({"parent": "Isso criaria um ciclo no menu."})

        # Um item so faz sentido apontando para o alvo do proprio tipo; limpar
        # os outros evita um produto "fantasma" preso num item que virou link.
        for candidate_type, (field, _message) in self.REQUIRED_BY_TYPE.items():
            if candidate_type != item_type and field in attrs and field != "url":
                attrs[field] = None if field != "image" else attrs[field]
        return attrs


def _is_descendant(candidate, ancestor):
    """`candidate` esta abaixo de `ancestor` na arvore?"""
    node = candidate
    depth = 0
    while node is not None and depth <= MenuItem.MAX_DEPTH + 1:
        if node.pk == ancestor.pk:
            return True
        node = node.parent
        depth += 1
    return False


class MenuItemTreeSerializer(MenuItemSerializer):
    """O item com os filhos aninhados — usado no detalhe do menu."""

    children = serializers.SerializerMethodField()

    def get_children(self, obj):
        children = [child for child in obj.children.all() if child.deleted_at is None]
        return MenuItemTreeSerializer(sorted(children, key=lambda c: c.display_order), many=True, context=self.context).data


class MenuSerializer(TenantModelSerializer):
    """Menu no estilo Shopify: um handle, um proposito e uma lista ordenada."""

    items = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()
    source_category_name = serializers.CharField(source="source_category.name", read_only=True)

    class Meta:
        model = Menu
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS
        # O handle e derivado do nome quando omitido (ver `validate`). Sem isto
        # o DRF exigia o campo antes de `validate` rodar e o fallback era morto.
        extra_kwargs = {"slug": {"required": False}}

    def get_items(self, obj):
        """So os itens de topo; os filhos vao aninhados dentro deles."""
        roots = [item for item in obj.items.all() if item.parent_id is None and item.deleted_at is None]
        return MenuItemTreeSerializer(
            sorted(roots, key=lambda item: item.display_order), many=True, context=self.context
        ).data

    def get_items_count(self, obj):
        return sum(1 for item in obj.items.all() if item.deleted_at is None)

    def validate_slug(self, value):
        slug = slugify(value or "")
        if not slug:
            raise serializers.ValidationError("Informe um apelido valido para o menu.")
        return slug

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get("slug") and not self.instance:
            attrs["slug"] = slugify(attrs.get("name", ""))[:140] or "menu"

        source = attrs.get("source") or getattr(self.instance, "source", Menu.SOURCE_MANUAL)
        category = attrs.get("source_category") or getattr(self.instance, "source_category", None)
        if source == Menu.SOURCE_CATEGORY_PRODUCTS and not category:
            raise serializers.ValidationError(
                {"source_category": "Escolha a categoria cujos produtos este menu vai listar."}
            )

        slug = attrs.get("slug") or getattr(self.instance, "slug", None)
        request = self.context.get("request")
        account = getattr(request, "account", None) if request else None
        if slug and account:
            duplicates = Menu.all_objects.filter(account=account, slug=slug, deleted_at__isnull=True)
            if self.instance:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError({"slug": "Ja existe um menu com este apelido nesta conta."})
        return attrs


class MenuResolvedSerializer(serializers.Serializer):
    """O menu ja RESOLVIDO — como o site o recebe.

    Existe para o editor pre-visualizar exatamente o que o bloco vai desenhar,
    inclusive nas origens dinamicas (onde nao ha item cadastrado para olhar).
    """

    def to_representation(self, instance):
        from apps.menu.services.menu_resolver import serialize_menu

        return serialize_menu(instance, request=self.context.get("request"))
