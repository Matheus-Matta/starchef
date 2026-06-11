from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin
from apps.core.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(TenantModelAdmin):
    list_display = ("created_at", "account", "action", "entity", "object_id", "restaurant", "branch", "actor")
    list_filter = ("account", "action", "entity", "restaurant", "branch")
    search_fields = ("entity", "object_id", "reason")
    readonly_fields = ("created_at", "updated_at")
