from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin
from apps.printers.models import Printer, PrintJob, Scale, ScaleReading


@admin.register(Printer)
class PrinterAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "sector", "driver_type", "auto_print", "is_active")
    list_filter = ("account", "restaurant", "branch", "driver_type", "sector", "is_active")


@admin.register(PrintJob)
class PrintJobAdmin(TenantModelAdmin):
    list_display = ("job_type", "account", "status", "order", "printer", "printed_by", "created_at")
    list_filter = ("account", "restaurant", "branch", "job_type", "status")


@admin.register(Scale)
class ScaleAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "protocol", "port", "product", "printer", "auto_print", "is_active")
    list_filter = ("account", "restaurant", "branch", "protocol", "is_active")
    search_fields = ("name", "port")


@admin.register(ScaleReading)
class ScaleReadingAdmin(TenantModelAdmin):
    list_display = ("scale", "account", "weight_kg", "tare_kg", "is_stable", "source", "order_item", "created_at")
    list_filter = ("account", "restaurant", "branch", "scale", "source", "is_stable")
