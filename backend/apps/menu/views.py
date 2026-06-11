from rest_framework import viewsets

from apps.core.mixins import AuditCreateUpdateMixin, TenantQuerySetMixin
from apps.menu.models import Ingredient, Product, ProductAddon, ProductCategory, ProductVariation
from apps.menu.serializers import (
    IngredientSerializer,
    ProductAddonSerializer,
    ProductCategorySerializer,
    ProductSerializer,
    ProductVariationSerializer,
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

