from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import AuditCreateUpdateMixin, TenantQuerySetMixin
from apps.menu.models import Ingredient, Menu, MenuItem, Product, ProductAddon, ProductCategory, ProductVariation, Recipe, RecipeItem
from apps.menu.serializers import (
    IngredientSerializer,
    MenuItemSerializer,
    MenuSerializer,
    ProductAddonSerializer,
    ProductCategorySerializer,
    ProductSerializer,
    ProductVariationSerializer,
    PublicMenuSerializer,
    RecipeItemSerializer,
    RecipeSerializer,
)


class ProductCategoryViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = ProductCategorySerializer
    queryset = ProductCategory.objects.select_related("restaurant", "branch", "parent").all()
    filterset_fields = ["restaurant", "branch", "parent", "is_active"]
    search_fields = ["name"]
    ordering_fields = ["display_order", "name"]


class ProductViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.select_related("restaurant", "branch", "category").prefetch_related("variations").all()
    filterset_fields = [
        "restaurant",
        "branch",
        "category",
        "product_type",
        "production_sector",
        "is_active",
        "available_for_table",
        "available_for_counter",
        "available_for_delivery",
    ]
    search_fields = ["name", "internal_code", "description"]
    ordering_fields = ["name", "sale_price", "created_at"]


class ProductAddonViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = ProductAddonSerializer
    queryset = ProductAddon.objects.select_related("restaurant", "branch").prefetch_related("products").all()
    filterset_fields = ["restaurant", "branch", "production_sector", "is_active"]
    search_fields = ["name"]


class ProductVariationViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = ProductVariationSerializer
    queryset = ProductVariation.objects.select_related("restaurant", "branch", "product").all()
    filterset_fields = ["restaurant", "branch", "product", "is_active"]
    search_fields = ["name", "product__name"]


class IngredientViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = IngredientSerializer
    queryset = Ingredient.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["restaurant", "branch", "unit", "is_active"]
    search_fields = ["name"]


class RecipeViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = RecipeSerializer
    queryset = Recipe.objects.select_related("restaurant", "branch", "product").prefetch_related("items__ingredient").all()
    filterset_fields = ["restaurant", "branch", "product", "is_active", "auto_deduct_stock"]
    search_fields = ["product__name"]

    def perform_update(self, serializer):
        instance = serializer.save()
        from apps.menu.services import recalculate_recipe_costs
        recalculate_recipe_costs(instance)


class RecipeItemViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = RecipeItemSerializer
    queryset = RecipeItem.objects.select_related("restaurant", "branch", "recipe__product", "ingredient").all()
    filterset_fields = ["restaurant", "branch", "recipe", "ingredient"]

    def _recalc(self, recipe):
        from apps.menu.services import recalculate_recipe_costs
        recalculate_recipe_costs(recipe)

    def perform_create(self, serializer):
        item = serializer.save()
        self._recalc(item.recipe)

    def perform_update(self, serializer):
        item = serializer.save()
        self._recalc(item.recipe)

    def perform_destroy(self, instance):
        recipe = instance.recipe
        instance.delete()
        self._recalc(recipe)


class MenuViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = MenuSerializer
    queryset = Menu.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["restaurant", "branch", "channel", "is_active"]
    search_fields = ["name", "slug"]


class MenuItemViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = MenuItemSerializer
    queryset = MenuItem.objects.select_related("restaurant", "branch", "menu", "product").all()
    filterset_fields = ["restaurant", "branch", "menu", "product", "is_active"]
    ordering_fields = ["display_order"]


class PublicMenuView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        try:
            menu = Menu.objects.get(slug=slug, is_active=True)
        except Menu.DoesNotExist:
            return Response({"detail": "Menu not found."}, status=404)
        return Response(PublicMenuSerializer(menu).data)

