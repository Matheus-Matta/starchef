from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer

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


class ProductCategorySerializer(TenantModelSerializer):
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


class ProductVariationSerializer(TenantModelSerializer):
    class Meta:
        model = ProductVariation
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class ProductAddonSerializer(TenantModelSerializer):
    class Meta:
        model = ProductAddon
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


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


class ProductSerializer(TenantModelSerializer):
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

    def get_category_name(self, obj):
        return obj.category.name if obj.category_id else "Sem categoria"

    def validate_sector(self, value):
        if value and self.instance and value.branch_id != self.instance.branch_id:
            raise serializers.ValidationError("O setor deve pertencer à mesma filial do produto.")
        return value

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
        return attrs


class IngredientSerializer(TenantModelSerializer):
    class Meta:
        model = Ingredient
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def validate_minimum_stock(self, value):
        # Opcional, mas não pode ser negativo quando informado (STC-031).
        if value is not None and value < 0:
            raise serializers.ValidationError("O estoque mínimo não pode ser negativo.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Nome único por filial — erro claro no campo em vez de 500/duplicidade (STC-033).
        name = attrs.get("name", getattr(self.instance, "name", None))
        branch = attrs.get("branch", getattr(self.instance, "branch", None))
        if name is not None:
            siblings = Ingredient.objects.filter(name__iexact=name)
            if branch is not None:
                siblings = siblings.filter(branch=branch)
            if self.instance is not None:
                siblings = siblings.exclude(pk=self.instance.pk)
            if siblings.exists():
                raise serializers.ValidationError({"name": "Já existe um ingrediente com este nome."})
        return attrs


class MenuItemSerializer(TenantModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    effective_price = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def get_effective_price(self, obj):
        return obj.override_price if obj.override_price is not None else obj.product.current_price


class MenuSerializer(TenantModelSerializer):
    items = MenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = Menu
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class PublicMenuProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    current_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    variations = ProductVariationSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = ["id", "name", "description", "image", "category", "category_name", "current_price", "variations", "allows_addons", "allows_notes", "requires_variation"]


class PublicMenuItemSerializer(serializers.ModelSerializer):
    product = PublicMenuProductSerializer(read_only=True)
    effective_price = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = ["id", "product", "display_order", "effective_price", "is_active"]

    def get_effective_price(self, obj):
        return obj.override_price if obj.override_price is not None else obj.product.current_price


class PublicMenuSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = ["id", "name", "slug", "channel", "available_from", "available_until", "items"]

    def get_items(self, obj):
        if hasattr(obj, "active_items"):
            return PublicMenuItemSerializer(obj.active_items, many=True).data
        active_items = obj.items.filter(is_active=True).select_related("product__category").prefetch_related("product__variations")
        return PublicMenuItemSerializer(active_items, many=True).data

