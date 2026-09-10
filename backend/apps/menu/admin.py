from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin, TenantTabularInline
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
    list_display = ("name", "account", "product", "price_delta", "is_active")
    list_filter = ("account", "restaurant", "branch", "is_active")


@admin.register(ProductAddon)
class ProductAddonAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "price", "production_sector", "is_active")
    list_filter = ("account", "restaurant", "branch", "production_sector", "is_active")


@admin.register(Ingredient)
class IngredientAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "unit", "supplier", "average_cost", "minimum_stock", "is_active")
    list_filter = ("account", "restaurant", "branch", "unit", "supplier", "is_active")
    search_fields = ("name",)


class RecipeItemInline(TenantTabularInline):
    model = RecipeItem
    extra = 0


@admin.register(Recipe)
class RecipeAdmin(TenantModelAdmin):
    list_display = ("product", "account", "yield_quantity", "total_cost", "auto_deduct_stock", "is_active")
    list_filter = ("account", "restaurant", "branch", "is_active")
    inlines = [RecipeItemInline]


class MenuItemInline(TenantTabularInline):
    model = MenuItem
    fk_name = "menu"
    extra = 0
    fields = ("item_type", "title", "product", "category", "url", "parent", "display_order", "is_active")


@admin.register(Menu)
class MenuAdmin(TenantModelAdmin):
    list_display = ("name", "slug", "menu_type", "source", "account", "branch", "channel", "is_active")
    list_filter = ("account", "restaurant", "branch", "menu_type", "source", "channel", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [MenuItemInline]


@admin.register(MenuItem)
class MenuItemAdmin(TenantModelAdmin):
    list_display = ("menu", "item_type", "label", "parent", "display_order", "is_active")
    list_filter = ("account", "restaurant", "branch", "menu", "item_type", "is_active")
    search_fields = ("title", "url", "product__name", "category__name")
