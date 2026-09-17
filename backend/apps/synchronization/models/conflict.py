"""SyncConflict: o que a regra automática não resolveu sozinha."""
from django.conf import settings
from django.db import models

from apps.core.models import UUIDModel
from apps.synchronization.constants import ConflictResolution, ConflictStatus


class SyncConflict(UUIDModel):
    """Duas versões do mesmo registro que a política não pôde decidir.

    Dado financeiro e fiscal NUNCA é resolvido em silêncio por last-write-wins:
    ele cai aqui e espera alguém decidir.
    """

    account = models.ForeignKey("accounts.Account", related_name="sync_conflicts", on_delete=models.PROTECT)
    event = models.ForeignKey(
        "synchronization.SyncEvent",
        related_name="conflicts",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    entity_type = models.CharField(max_length=80, db_index=True)
    entity_id = models.CharField(max_length=64, db_index=True)
    source_node = models.ForeignKey(
        "synchronization.SyncNode", related_name="conflicts_as_source", on_delete=models.PROTECT
    )
    target_node = models.ForeignKey(
        "synchronization.SyncNode", related_name="conflicts_as_target", on_delete=models.PROTECT
    )

    local_version = models.BigIntegerField(default=0)
    remote_version = models.BigIntegerField(default=0)
    local_payload = models.JSONField(default=dict, blank=True)
    remote_payload = models.JSONField(default=dict, blank=True)

    resolution = models.CharField(
        max_length=14, choices=ConflictResolution.CHOICES, default=ConflictResolution.MANUAL
    )
    status = models.CharField(max_length=10, choices=ConflictStatus.CHOICES, default=ConflictStatus.OPEN)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Conflito de sincronização"
        verbose_name_plural = "Conflitos de sincronização"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["account", "status"]),
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self):
        return f"{self.entity_type}/{self.entity_id} [{self.status}]"
