"""SyncEvent: a outbox/inbox durável. É ela que garante que nada se perde."""
import uuid

from django.db import models
from django.utils import timezone

from apps.core.models import UUIDModel
from apps.synchronization.constants import (
    PROTOCOL_VERSION,
    SCHEMA_VERSION,
    Direction,
    EventStatus,
    Operation,
)


class SyncEventQuerySet(models.QuerySet):
    def pending_outbound(self, node):
        """O que ainda precisa sair deste nó, na ordem em que foi gerado."""
        agora = timezone.now()
        return (
            self.filter(
                direction=Direction.OUTBOUND,
                source_node=node,
                status__in=[EventStatus.PENDING, EventStatus.FAILED],
            )
            .filter(models.Q(next_attempt_at__isnull=True) | models.Q(next_attempt_at__lte=agora))
            .order_by("sequence")
        )

    def pending_inbound(self, node):
        """O que chegou e ainda não foi aplicado neste nó."""
        agora = timezone.now()
        return (
            self.filter(
                direction=Direction.INBOUND,
                target_node=node,
                status__in=[EventStatus.RECEIVED, EventStatus.FAILED],
            )
            .filter(models.Q(next_attempt_at__isnull=True) | models.Q(next_attempt_at__lte=agora))
            .order_by("sequence")
        )

    def pending_for_target(self, target):
        """O que está esperando para ir até ESTE destino.

        Filtrar por destino em vez de por origem é o que torna o despacho
        imune a uma instalação com mais de um nó `is_self` — todo evento
        OUTBOUND que existe aqui foi criado por esta instalação, então a
        pergunta útil é "para quem vai", não "quem gerou".
        """
        agora = timezone.now()
        return (
            self.filter(
                direction=Direction.OUTBOUND,
                target_node=target,
                status__in=[EventStatus.PENDING, EventStatus.FAILED],
            )
            .filter(models.Q(next_attempt_at__isnull=True) | models.Q(next_attempt_at__lte=agora))
            .order_by("sequence")
        )

    def unconfirmed(self, node):
        """Saiu daqui mas ninguém confirmou — o que a reconexão reenvia."""
        return self.filter(
            direction=Direction.OUTBOUND,
            source_node=node,
            status__in=[EventStatus.SENT, EventStatus.RECEIVED, EventStatus.APPLIED],
        ).order_by("sequence")


class SyncEvent(UUIDModel):
    """Um evento durável, sempre gravado na MESMA transação do dado que o gerou.

    Enquanto o status não for ACKNOWLEDGED (saída) ou APPLIED (entrada), o
    evento continua aqui com o payload inteiro: é daqui que a retomada e o
    reprocessamento manual leem. Nada é apagado antes da retenção.
    """

    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    account = models.ForeignKey("accounts.Account", related_name="sync_events", on_delete=models.PROTECT)
    source_node = models.ForeignKey(
        "synchronization.SyncNode", related_name="events_sent", on_delete=models.PROTECT
    )
    target_node = models.ForeignKey(
        "synchronization.SyncNode", related_name="events_received", on_delete=models.PROTECT
    )
    run = models.ForeignKey(
        "synchronization.SyncRun",
        related_name="events",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    direction = models.CharField(max_length=8, choices=Direction.CHOICES, db_index=True)
    sequence = models.BigIntegerField()

    entity_type = models.CharField(max_length=80, db_index=True)
    entity_id = models.CharField(max_length=64, db_index=True)
    operation = models.CharField(max_length=10, choices=Operation.CHOICES)
    entity_version = models.BigIntegerField(default=1)
    protocol_version = models.PositiveIntegerField(default=PROTOCOL_VERSION)
    schema_version = models.PositiveIntegerField(default=SCHEMA_VERSION)

    payload = models.JSONField(default=dict)
    payload_checksum = models.CharField(max_length=64)

    status = models.CharField(max_length=14, choices=EventStatus.CHOICES, default=EventStatus.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error = models.TextField(blank=True)
    correlation_id = models.UUIDField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    objects = SyncEventQuerySet.as_manager()

    class Meta:
        verbose_name = "Evento de sincronização"
        verbose_name_plural = "Eventos de sincronização"
        ordering = ["sequence", "created_at"]
        constraints = [
            # A sequência é por origem E direção: o mesmo evento existe dos dois
            # lados (OUTBOUND aqui, INBOUND lá) com a mesma origem e sequência.
            models.UniqueConstraint(
                fields=["source_node", "direction", "sequence"], name="sync_unique_sequence_per_source"
            )
        ]
        indexes = [
            models.Index(fields=["account", "status", "created_at"]),
            models.Index(fields=["target_node", "status"]),
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["status", "next_attempt_at"]),
        ]

    def __str__(self):
        return f"{self.entity_type}/{self.entity_id} #{self.sequence} [{self.status}]"

    @property
    def is_terminal(self):
        return self.status in EventStatus.TERMINAL
