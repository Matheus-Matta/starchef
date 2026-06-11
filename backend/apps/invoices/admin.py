from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin
from apps.invoices.models import Invoice


@admin.register(Invoice)
class InvoiceAdmin(TenantModelAdmin):
    list_display = ("order", "account", "phase", "status", "number", "provider", "issued_at")
    list_filter = ("account", "restaurant", "branch", "phase", "status")
    search_fields = ("number", "provider", "order__sequence")
