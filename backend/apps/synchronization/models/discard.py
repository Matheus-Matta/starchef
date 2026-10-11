from django.conf import settings
from django.db import models

from apps.core.models import UUIDModel


class SyncDiscard(UUIDModel):
    """O que chegou e foi IGNORADO — guardado para dar para recuperar.

    Loja e nuvem aceitam escrever e quem decide é a versão: o mais novo vence,
    o mais velho é ignorado, o reenvio devolve o que já existe. Ignorar é o
    certo; jogar fora sem registro não é. Aqui fica o que chegou (`dados`), por
    que foi ignorado e as duas versões. Nada nesta tabela é usado pela
    operação: é o histórico de cada nó, para conferir e recuperar.
    """

    ORIGEM_API = "api"
    ORIGEM_SYNC = "sync"
    ORIGEM_CHOICES = [(ORIGEM_API, "Requisição da API"), (ORIGEM_SYNC, "Sincronização")]

    MOTIVO_VERSAO_MAIS_VELHA = "versao_mais_velha"
    MOTIVO_REENVIO = "reenvio"
    MOTIVO_EXCLUSAO_MAIS_VELHA = "exclusao_mais_velha"
    MOTIVO_APAGADO_DEPOIS = "apagado_depois"
    MOTIVO_ANOTACAO_PERDEU_VINCULO = "anotacao_perdeu_vinculo"
    MOTIVO_CHOICES = [
        (MOTIVO_VERSAO_MAIS_VELHA, "Versão mais velha que a gravada"),
        (MOTIVO_REENVIO, "Reenvio do que já existe"),
        (MOTIVO_EXCLUSAO_MAIS_VELHA, "Exclusão mais velha que uma edição"),
        (MOTIVO_APAGADO_DEPOIS, "Registro apagado aqui depois"),
        (MOTIVO_ANOTACAO_PERDEU_VINCULO, "Anotação de comanda cobrada nos dois lados"),
    ]

    account = models.ForeignKey(
        "accounts.Account", related_name="sync_discards", null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    origem = models.CharField(max_length=8, choices=ORIGEM_CHOICES, db_index=True)
    motivo = models.CharField(max_length=32, choices=MOTIVO_CHOICES, db_index=True)
    entity_type = models.CharField(max_length=80, db_index=True)
    entity_id = models.CharField(max_length=64, db_index=True)
    dados = models.JSONField(default=dict, blank=True)
    versao_recebida = models.BigIntegerField(default=0)
    versao_local = models.BigIntegerField(default=0)
    event = models.ForeignKey(
        "synchronization.SyncEvent", related_name="discards", null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="sync_discards", null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Requisição ignorada"
        verbose_name_plural = "Requisições ignoradas"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def __str__(self):
        return f"{self.get_motivo_display()}: {self.entity_type}/{self.entity_id}"
