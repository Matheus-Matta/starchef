from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin, TenantTabularInline
from apps.orders.models import Order, OrderItem, OrderItemAddon


class OrderItemInline(TenantTabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(TenantModelAdmin):
    list_display = ("sequence", "account", "branch", "order_type", "status", "payment_status", "total", "opened_at")
    list_filter = ("account", "restaurant", "branch", "order_type", "status", "payment_status")
    search_fields = ("sequence", "customer__name", "table__number")
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(TenantModelAdmin):
    list_display = ("order", "account", "product", "quantity", "status", "production_sector", "launched_at")
    list_filter = ("account", "restaurant", "branch", "production_sector", "status")


@admin.register(OrderItemAddon)
class OrderItemAddonAdmin(TenantModelAdmin):
    list_display = ("item", "account", "addon", "quantity", "total_price")
    list_filter = ("account", "restaurant", "branch")
