from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin
from apps.printers.models import Printer, PrintJob


@admin.register(Printer)
class PrinterAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "sector", "driver_type", "auto_print", "is_active")
    list_filter = ("account", "restaurant", "branch", "driver_type", "sector", "is_active")


@admin.register(PrintJob)
class PrintJobAdmin(TenantModelAdmin):
    list_display = ("job_type", "account", "status", "order", "printer", "printed_by", "created_at")
    list_filter = ("account", "restaurant", "branch", "job_type", "status")
