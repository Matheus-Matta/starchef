from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin
from apps.kitchen.models import KdsItemPosition, KdsStation


@admin.register(KdsStation)
class KdsStationAdmin(TenantModelAdmin):
    list_display = ("name", "account", "restaurant", "branch", "sla_minutes", "is_active")
    list_filter = ("account", "restaurant", "branch", "is_active")
    search_fields = ("name",)


@admin.register(KdsItemPosition)
class KdsItemPositionAdmin(TenantModelAdmin):
    list_display = ("station", "item", "column", "entered_at")
    list_filter = ("station", "column")
