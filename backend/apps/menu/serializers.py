from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer

from apps.menu.models import (
    Ingredient,
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

