"""SyncNode: quem é cada ponta do vínculo e qual o estado dela."""
import uuid

from django.db import models

from apps.core.models import TimeStampedModel
from apps.synchronization.constants import (
    ENVIRONMENT_CHOICES,
    ENVIRONMENT_DEVELOPMENT,
    NodeStatus,
    NodeType,
)


class SyncNode(TimeStampedModel):
    """Cadastro de uma instalação (loja ou nuvem) que participa da sincronização.

    Os dois lados do mesmo vínculo compartilham `pair_id`; o `id` identifica a
    instalação específica. A nuvem guarda um registro por backend local; o
    backend local guarda a própria identidade e o peer da nuvem.
    """

    pair_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    account = models.ForeignKey(
        "accounts.Account",
        related_name="sync_nodes",
        on_delete=models.PROTECT,
    )
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        related_name="sync_nodes",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    node_type = models.CharField(max_length=8, choices=NodeType.CHOICES, db_index=True)
    environment = models.CharField(
        max_length=16, choices=ENVIRONMENT_CHOICES, default=ENVIRONMENT_DEVELOPMENT
    )
    name = models.CharField(max_length=120)
    endpoint = models.URLField(blank=True, help_text="URL WSS que o nó local procura.")
    allowed_ip = models.GenericIPAddressField(
        null=True, blank=True, help_text="Restrição adicional. Nunca é a autenticação principal."
    )

    # Credencial. O token puro só existe uma vez, na tela de provisionamento; o
    # banco guarda o hash. A chave AES é outra coisa: o banco guarda apenas o
    # identificador e a impressão digital — nunca a chave.
    credential_hash = models.CharField(max_length=128, blank=True)
    credential_rotated_at = models.DateTimeField(null=True, blank=True)
    encryption_key_id = models.CharField(max_length=64, blank=True)
    secret_fingerprint = models.CharField(max_length=64, blank=True)

    status = models.CharField(max_length=10, choices=NodeStatus.CHOICES, default=NodeStatus.PENDING)
    app_version = models.CharField(max_length=32, blank=True)
    schema_version = models.PositiveIntegerField(default=0)
    protocol_version = models.PositiveIntegerField(default=0)

    last_seen_at = models.DateTimeField(null=True, blank=True)
    #: Quando este nó perdeu contato com o outro lado na queda mais recente.
    #:
    #: É o `last_seen_at` de ANTES da reconexão, guardado no momento em que ela
    #: acontece. Serve para responder a pergunta que decide um conflito: "a
    #: loja chegou a mexer nesta linha enquanto esteve fora?". Se a versão
    #: local é anterior a isto, ela não mexeu — o que chega da nuvem não é
    #: edição concorrente, é atualização que a loja perdeu.
    #:
    #: Guardar o último contato, e não o instante da queda, é o que faz isso
    #: sobreviver a um processo morto: ninguém escreve nada quando o container
    #: é derrubado, mas o último contato bem-sucedido já está gravado.
    offline_since = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sent_cursor = models.BigIntegerField(default=0)
    last_received_cursor = models.BigIntegerField(default=0)
    #: Próxima sequência que este nó vai atribuir aos eventos que ele origina.
    sequence_counter = models.BigIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    #: Marcado quando este registro representa a PRÓPRIA instalação.
    is_self = models.BooleanField(default=False)
    #: O nó do outro lado. ForeignKey, não OneToOne: a nuvem tem UMA
    #: identidade e N lojas apontando para ela. Modelar isto como 1-para-1
    #: obrigava a nuvem a criar um nó "este" por loja — que era exatamente o
    #: defeito que fazia o despacho devolver lote vazio (ver
    #: `provisioning.ensure_self_node`). Do lado da loja continua havendo um
    #: só, porque a loja fala com uma nuvem.
    peer = models.ForeignKey(
        "self", null=True, blank=True, related_name="peers", on_delete=models.SET_NULL
    )
    last_error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Nó de sincronização"
        verbose_name_plural = "Nós de sincronização"
        ordering = ["account", "node_type", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["pair_id", "node_type"], name="sync_unique_node_type_per_pair"
            )
        ]
        indexes = [
            models.Index(fields=["account", "status"]),
            models.Index(fields=["node_type", "is_active"]),
        ]
        permissions = [
            ("can_start_full_sync", "Pode iniciar sincronização completa"),
            ("can_provision_node", "Pode gerar credenciais de nó"),
            ("can_revoke_node", "Pode revogar um nó"),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_node_type_display()})"

    @property
    def can_connect(self):
        return self.is_active and self.status in NodeStatus.CONNECTABLE

    @property
    def group_name(self):
        """Grupo exclusivo do Channels. Nunca há broadcast fora dele."""
        return f"sync.account.{self.account_id}.node.{self.id}"

    def next_sequence(self):
        """Reserva a próxima sequência deste nó. Use dentro de uma transação."""
        updated = SyncNode.objects.filter(pk=self.pk).update(
            sequence_counter=models.F("sequence_counter") + 1
        )
        if not updated:  # pragma: no cover — nó apagado no meio da transação
            raise SyncNode.DoesNotExist(f"Nó {self.pk} não existe mais")
        self.refresh_from_db(fields=["sequence_counter"])
        return self.sequence_counter
