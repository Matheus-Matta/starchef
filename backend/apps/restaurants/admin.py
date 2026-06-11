from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin
from apps.restaurants.models import Branch, Command, Restaurant, Table, TableSector


@admin.register(Restaurant)
class RestaurantAdmin(TenantModelAdmin):
    list_display = ("trade_name", "account", "cnpj", "city", "state", "is_active")
    search_fields = ("trade_name", "legal_name", "cnpj")
    list_filter = ("account", "is_active", "state")


@admin.register(Branch)
class BranchAdmin(TenantModelAdmin):
    list_display = ("name", "account", "restaurant", "cnpj", "is_active")
    search_fields = ("name", "cnpj", "restaurant__trade_name")
    list_filter = ("account", "restaurant", "is_active")


@admin.register(TableSector)
class TableSectorAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "display_order", "is_active")
    list_filter = ("account", "restaurant", "branch", "is_active")


@admin.register(Table)
class TableAdmin(TenantModelAdmin):
    list_display = ("number", "account", "sector", "branch", "capacity", "status")
    list_filter = ("account", "branch", "status")
    search_fields = ("number",)


@admin.register(Command)
class CommandAdmin(TenantModelAdmin):
    list_display = ("code", "account", "branch", "customer_name", "status", "is_active")
    list_filter = ("account", "branch", "status", "is_active")
