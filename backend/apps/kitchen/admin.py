from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin
from apps.kitchen.models import KdsStation


@admin.register(KdsStation)
class KdsStationAdmin(TenantModelAdmin):
    list_display = ("name", "account", "restaurant", "branch", "sla_minutes", "is_active")
    list_filter = ("account", "restaurant", "branch", "is_active")
    search_fields = ("name",)
