from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin
from apps.stock.models import StockLocation, StockMovement, Supplier


@admin.register(Supplier)
class SupplierAdmin(TenantModelAdmin):
    list_display = ("name", "account", "tax_id", "phone", "email", "is_active")
    list_filter = ("account", "is_active")
    search_fields = ("name", "legal_name", "tax_id", "contact_name")


@admin.register(StockLocation)
class StockLocationAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "is_active")
    list_filter = ("account", "restaurant", "branch", "is_active")


@admin.register(StockMovement)
class StockMovementAdmin(TenantModelAdmin):
    list_display = ("ingredient", "account", "location", "movement_type", "quantity", "operator", "created_at")
    list_filter = ("account", "restaurant", "branch", "movement_type", "location")
