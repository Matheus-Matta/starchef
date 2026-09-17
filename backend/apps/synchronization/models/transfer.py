"""SyncFileTransfer: o binário que não cabe no JSON do WebSocket (§16).

Imagem, XML e PDF não viajam dentro do evento. O evento leva os METADADOS —
nome, tamanho, MIME e SHA-256 — e o arquivo vem por HTTPS autenticado, em
pedaços, com retomada por offset.

O registro existe porque a transferência precisa sobreviver à queda: sem ele,
uma foto de 4 MB interrompida aos 3,5 MB recomeçaria do zero toda vez que a
rede oscilasse.
"""
from django.db import models

from apps.core.models import UUIDModel


class TransferStatus:
    PENDING = "PENDING"
    RECEIVING = "RECEIVING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CHOICES = [
        (PENDING, "Aguardando o primeiro pedaço"),
        (RECEIVING, "Recebendo"),
        (VALIDATING, "Conferindo checksum"),
        (COMPLETED, "Concluída"),
        (FAILED, "Falhou"),
    ]
    ABERTAS = {PENDING, RECEIVING, VALIDATING}


class SyncFileTransfer(UUIDModel):
    """Uma transferência de arquivo entre dois nós, retomável por offset."""

    account = models.ForeignKey(
        "accounts.Account", related_name="sync_transfers", on_delete=models.PROTECT
    )
    source_node = models.ForeignKey(
        "synchronization.SyncNode", related_name="transfers_sent", on_delete=models.PROTECT
    )
    target_node = models.ForeignKey(
        "synchronization.SyncNode", related_name="transfers_received", on_delete=models.PROTECT
    )

    #: A quem o arquivo pertence. O vínculo só é feito DEPOIS da validação.
    entity_type = models.CharField(max_length=80, db_index=True)
    entity_id = models.CharField(max_length=64, db_index=True)
    field_name = models.CharField(max_length=80)

    #: Caminho relativo dentro do storage de mídia, igual nos dois lados.
    storage_path = models.CharField(max_length=500)
    content_type = models.CharField(max_length=120, blank=True)
    total_bytes = models.BigIntegerField()
    received_bytes = models.BigIntegerField(default=0)
    #: SHA-256 do arquivo INTEIRO, calculado na origem.
    checksum = models.CharField(max_length=64)

    status = models.CharField(
        max_length=12, choices=TransferStatus.CHOICES, default=TransferStatus.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    #: Onde os pedaços se acumulam até o arquivo fechar. Nunca é o destino final.
    temp_path = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Transferência de arquivo"
        verbose_name_plural = "Transferências de arquivo"
        ordering = ["-created_at"]
        constraints = [
            # Uma transferência aberta por arquivo e destino. Duas em paralelo
            # gravariam no mesmo temporário e produziriam um arquivo picado.
            models.UniqueConstraint(
                fields=["target_node", "storage_path", "checksum"],
                condition=models.Q(status__in=["PENDING", "RECEIVING", "VALIDATING"]),
                name="sync_unique_open_transfer",
            )
        ]
        indexes = [
            models.Index(fields=["account", "status"]),
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self):
        return f"{self.storage_path} ({self.received_bytes}/{self.total_bytes})"

    @property
    def is_complete(self):
        return self.received_bytes >= self.total_bytes

    @property
    def progress_percent(self):
        if not self.total_bytes:
            return 0
        return min(100, round(self.received_bytes * 100 / self.total_bytes))
