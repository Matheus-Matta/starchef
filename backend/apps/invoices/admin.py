from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin, TenantTabularInline
from apps.invoices.models import FiscalConfig, FiscalProfile, Invoice, InvoiceItem


class InvoiceItemInline(TenantTabularInline):
    model = InvoiceItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(TenantModelAdmin):
    list_display = ("number", "account", "document_model", "status", "provider", "total_amount", "issued_at")
    list_filter = ("account", "restaurant", "branch", "phase", "status", "document_model")
    search_fields = ("number", "provider", "access_key", "order__sequence")
    inlines = [InvoiceItemInline]


@admin.register(FiscalConfig)
class FiscalConfigAdmin(TenantModelAdmin):
    list_display = ("branch", "account", "document_model", "environment", "series", "next_number", "provider", "is_active")
    list_filter = ("account", "restaurant", "branch", "document_model", "environment", "is_active")
    search_fields = ("cnpj", "corporate_name", "trade_name")
    exclude = (
        "provider_token",
        "csc_token",
        "focus_token_production",
        "focus_token_homologation",
        "focus_certificate_base64",
        "focus_certificate_password",
    )
    readonly_fields = ("focus_company_id", "focus_sync_status", "focus_sync_error", "focus_synced_at")


@admin.register(FiscalProfile)
class FiscalProfileAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "ncm", "cfop", "csosn", "cst_icms", "is_default", "is_active")
    list_filter = ("account", "restaurant", "branch", "is_default", "is_active")
    search_fields = ("name", "ncm", "cfop")
