from django.db import models

from apps.core.models import TenantModel


class Invoice(TenantModel):
    PHASE_RECEIPT = "receipt"
    PHASE_FISCAL = "fiscal"

    STATUS_DRAFT = "draft"
    STATUS_ISSUED = "issued"
    STATUS_CANCELLED = "cancelled"
    STATUS_ERROR = "error"

    order = models.OneToOneField("orders.Order", related_name="invoice", on_delete=models.PROTECT)
    phase = models.CharField(max_length=20, default=PHASE_RECEIPT)
    status = models.CharField(max_length=20, default=STATUS_DRAFT, db_index=True)
    number = models.CharField(max_length=60, blank=True)
    provider = models.CharField(max_length=80, blank=True)
    fiscal_payload = models.JSONField(default=dict, blank=True)
    xml_content = models.TextField(blank=True)
    danfe_url = models.URLField(blank=True)
    error_message = models.TextField(blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["branch", "status", "created_at"]),
        ]

    def __str__(self):
        return f"Invoice {self.number or self.id}"

