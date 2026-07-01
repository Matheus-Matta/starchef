from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer

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
    class Meta:
        model = ProductCategory
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class ProductVariationSerializer(TenantModelSerializer):
    class Meta:
        model = ProductVariation
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class ProductAddonSerializer(TenantModelSerializer):
    class Meta:
        model = ProductAddon
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class RecipeItemSerializer(TenantModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)

    class Meta:
        model = RecipeItem
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class RecipeSerializer(TenantModelSerializer):
    items = RecipeItemSerializer(many=True, read_only=True)

    class Meta:
        model = Recipe
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by", "total_cost"]


class ProductSerializer(TenantModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    current_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    variations = ProductVariationSerializer(many=True, read_only=True)
    recipe = RecipeSerializer(read_only=True)

    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class IngredientSerializer(TenantModelSerializer):
    class Meta:
        model = Ingredient
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class MenuItemSerializer(TenantModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    effective_price = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]

    def get_effective_price(self, obj):
        return obj.override_price if obj.override_price is not None else obj.product.current_price


class MenuSerializer(TenantModelSerializer):
    items = MenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = Menu
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class PublicMenuProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    current_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    variations = ProductVariationSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = ["id", "name", "description", "image", "category", "category_name", "current_price", "variations", "allows_addons", "allows_notes"]


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
        active_items = obj.items.filter(is_active=True).select_related("product__category").prefetch_related("product__variations")
        return PublicMenuItemSerializer(active_items, many=True).data

