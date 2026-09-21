from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin, TenantTabularInline
from apps.orders.models import OrderBatch, OrderItem


class OrderItemInline(TenantTabularInline):
    model = OrderItem
    extra = 0



@admin.register(OrderBatch)
class OrderBatchAdmin(TenantModelAdmin):
    list_display = ("order", "account", "batch_number", "status", "sent_by", "sent_at", "printed_at")
    list_filter = ("account", "restaurant", "branch", "status")
