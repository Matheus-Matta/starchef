from django.conf import settings
from django.db import models

from apps.core.models import TenantBaseModel


class ImportJob(TenantBaseModel):
    """Uma importação de planilha processada em segundo plano.

    A tela mandava uma requisição por linha e esperava cada uma: com 500
    linhas, ficava presa por minutos. Agora ela entrega o lote inteiro aqui e
    segue; o worker processa e o resultado chega pelo sino.
    """

    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Na fila"),
        (STATUS_RUNNING, "Processando"),
        (STATUS_DONE, "Concluída"),
        (STATUS_FAILED, "Falhou"),
    ]

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="import_jobs"
    )
    # Rota da listagem que a tela usaria, ex.: "/menu/products/".
    endpoint = models.CharField(max_length=200)
    key_field = models.CharField(max_length=60, blank=True)
    # O restaurante escolhido na barra da web, repassado às gravações.
    restaurant_scope = models.CharField(max_length=64, blank=True)
    rows = models.JSONField(default=list)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_QUEUED, db_index=True)
    total = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Importação {self.endpoint} ({self.status})"
