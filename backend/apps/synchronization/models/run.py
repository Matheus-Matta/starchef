"""SyncRun: uma carga (bootstrap/total) com progresso auditável."""
from django.conf import settings
from django.db import models

from apps.core.models import UUIDModel
from apps.synchronization.constants import RunStatus, RunType


class SyncRun(UUIDModel):
    """Histórico e progresso de uma carga completa ou de bootstrap.

    Existe separada do SyncEvent de propósito: misturar fila, tentativas e
    progresso de carga numa tabela só torna impossível responder "em que pé
    está a carga de ontem" sem varrer milhões de eventos.
    """

    account = models.ForeignKey("accounts.Account", related_name="sync_runs", on_delete=models.PROTECT)
    source_node = models.ForeignKey(
        "synchronization.SyncNode", related_name="runs_as_source", on_delete=models.PROTECT
    )
    target_node = models.ForeignKey(
        "synchronization.SyncNode", related_name="runs_as_target", on_delete=models.PROTECT
    )
    run_type = models.CharField(max_length=12, choices=RunType.CHOICES)
    status = models.CharField(max_length=12, choices=RunStatus.CHOICES, default=RunStatus.PENDING)

    #: Sequência da origem no instante do snapshot. Tudo depois dela é
    #: reproduzido como incremental quando a carga termina.
    snapshot_cursor = models.BigIntegerField(default=0)
    manifest = models.JSONField(default=dict, blank=True)
    current_entity = models.CharField(max_length=80, blank=True)

    total_entities = models.PositiveIntegerField(default=0)
    processed_entities = models.PositiveIntegerField(default=0)
    total_records = models.BigIntegerField(default=0)
    processed_records = models.BigIntegerField(default=0)
    failed_records = models.BigIntegerField(default=0)
    total_bytes = models.BigIntegerField(default=0)
    processed_bytes = models.BigIntegerField(default=0)

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    initiated_ip = models.GenericIPAddressField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Carga de sincronização"
        verbose_name_plural = "Cargas de sincronização"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["account", "status"]),
            models.Index(fields=["target_node", "status"]),
        ]

    def __str__(self):
        return f"{self.get_run_type_display()} -> {self.target_node_id} [{self.status}]"

    @property
    def is_busy(self):
        return self.status in RunStatus.BUSY

    @property
    def progress_percent(self):
        if not self.total_records:
            return 0
        return min(100, round(self.processed_records * 100 / self.total_records))
