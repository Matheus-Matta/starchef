from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin, TenantTabularInline
from apps.menu.models import Ingredient, Product, ProductAddon, ProductCategory, ProductVariation, Recipe, RecipeItem


@admin.register(ProductCategory)
class ProductCategoryAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "parent", "display_order", "is_active")
    list_filter = ("account", "restaurant", "branch", "is_active")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(TenantModelAdmin):
    list_display = ("name", "account", "internal_code", "category", "sale_price", "production_sector", "is_active")
    list_filter = ("account", "restaurant", "branch", "product_type", "production_sector", "is_active")
    search_fields = ("name", "internal_code", "description")


@admin.register(ProductVariation)
class ProductVariationAdmin(TenantModelAdmin):
    list_display = ("name", "account", "product", "price_delta", "is_required", "is_active")
    list_filter = ("account", "restaurant", "branch", "is_active")


@admin.register(ProductAddon)
class ProductAddonAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "price", "production_sector", "is_active")
    list_filter = ("account", "restaurant", "branch", "production_sector", "is_active")


@admin.register(Ingredient)
class IngredientAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "unit", "average_cost", "minimum_stock", "is_active")
    list_filter = ("account", "restaurant", "branch", "unit", "is_active")
    search_fields = ("name",)


class RecipeItemInline(TenantTabularInline):
    model = RecipeItem
    extra = 0


@admin.register(Recipe)
class RecipeAdmin(TenantModelAdmin):
    list_display = ("product", "account", "yield_quantity", "total_cost", "auto_deduct_stock", "is_active")
    list_filter = ("account", "restaurant", "branch", "is_active")
    inlines = [RecipeItemInline]
