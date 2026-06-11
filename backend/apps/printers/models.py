from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Printer(TenantModel):
    DRIVER_BROWSER = "browser"
    DRIVER_ESCPOS = "escpos"

    DRIVER_CHOICES = [
        (DRIVER_BROWSER, "Browser"),
        (DRIVER_ESCPOS, "ESC/POS"),
    ]

    name = models.CharField(max_length=120)
    sector = models.CharField(max_length=24, blank=True)
    driver_type = models.CharField(max_length=24, choices=DRIVER_CHOICES, default=DRIVER_BROWSER)
    endpoint = models.CharField(max_length=255, blank=True)
    auto_print = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_printer_by_branch"),
        ]

    def __str__(self):
        return self.name


class PrintJob(TenantModel):
    TYPE_KITCHEN = "kitchen_ticket"
    TYPE_BAR = "bar_ticket"
    TYPE_TABLE_BILL = "table_bill"
    TYPE_RECEIPT = "receipt"
    TYPE_PAYMENT = "payment_receipt"
    TYPE_CASH_CLOSE = "cash_close"

    STATUS_PENDING = "pending"
    STATUS_RENDERED = "rendered"
    STATUS_PRINTED = "printed"
    STATUS_FAILED = "failed"

    printer = models.ForeignKey(Printer, null=True, blank=True, related_name="jobs", on_delete=models.SET_NULL)
    order = models.ForeignKey("orders.Order", null=True, blank=True, related_name="print_jobs", on_delete=models.SET_NULL)
    job_type = models.CharField(max_length=32, default=TYPE_RECEIPT, db_index=True)
    status = models.CharField(max_length=24, default=STATUS_RENDERED, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    html_content = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    printed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="print_jobs",
        on_delete=models.SET_NULL,
    )
    printed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["branch", "job_type", "status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.job_type} - {self.status}"

