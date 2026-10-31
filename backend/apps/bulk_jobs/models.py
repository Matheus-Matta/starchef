from django.conf import settings
from django.db import models

from apps.core.models import TenantBaseModel


class BulkJob(TenantBaseModel):
    """Uma operação pesada entregue ao worker sem prender a tela."""

    COMMAND_RESET = "command_reset"
    ORDER_CANCEL = "order_cancel"
    ORDER_DELETE = "order_delete"
    INVOICE_RESEND = "invoice_resend"
    INBOUND_RECONCILE = "inbound_reconcile"
    INBOUND_XML_IMPORT = "inbound_xml_import"
    ACTION_CHOICES = [
        (COMMAND_RESET, "Zerar comandas"),
        (ORDER_CANCEL, "Cancelar pedidos"),
        (ORDER_DELETE, "Excluir pedidos"),
        (INVOICE_RESEND, "Reenviar NFC-e"),
        (INBOUND_RECONCILE, "Conciliar NF-e de entrada"),
        (INBOUND_XML_IMPORT, "Importar XML de entrada"),
    ]

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    STATUS_CHOICES = [
        (QUEUED, "Na fila"),
        (RUNNING, "Processando"),
        (DONE, "Concluída"),
        (FAILED, "Falhou"),
    ]

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="bulk_jobs",
    )
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    payload = models.JSONField(default=dict)
    result = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=QUEUED, db_index=True)
    worker_task_id = models.CharField(max_length=64, blank=True)
    total = models.PositiveIntegerField(default=0)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class BulkJobFile(TenantBaseModel):
    """Arquivo temporário que precisa sobreviver até o worker abrir o job."""

    job = models.ForeignKey(BulkJob, related_name="files", on_delete=models.CASCADE)
    file = models.FileField(upload_to="bulk_jobs/%Y/%m/%d/")
    original_name = models.CharField(max_length=255)
