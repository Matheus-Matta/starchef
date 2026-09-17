"""SyncDirty: a marca que a trigger deixa quando o ORM foi contornado.

Signals do Django não veem `QuerySet.update`, `bulk_create`, `bulk_update` nem
SQL direto (§11.2). Uma promoção aplicada com um `update()` em mil produtos
simplesmente não geraria evento nenhum — e ninguém perceberia até a loja
vender pelo preço velho.

A trigger no PostgreSQL fecha esse buraco. Ela **não** monta o evento: montar
o payload em PL/pgSQL significaria reescrever a serialização do Python em
outra linguagem e mantê-las iguais para sempre — elas divergiriam na primeira
mudança de campo, silenciosamente. A trigger só anota "esta linha mudou", e
uma tarefa Python transforma a anotação em evento de verdade, com a mesma
serialização de sempre.
"""
from django.db import models

from apps.core.models import UUIDModel


class SyncDirty(UUIDModel):
    """Uma linha que mudou por fora do ORM e ainda não virou evento."""

    #: Nome da tabela, como o PostgreSQL a conhece. A trigger não sabe o que é
    #: um "entity_type" — quem traduz é o Python, pelo registro.
    table_name = models.CharField(max_length=120, db_index=True)
    row_id = models.CharField(max_length=64, db_index=True)
    operation = models.CharField(max_length=10)
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    processed_at = models.DateTimeField(null=True, blank=True)
    #: O evento que nasceu desta marca, quando nasceu.
    event = models.ForeignKey(
        "synchronization.SyncEvent",
        related_name="from_dirty",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Marca de alteração fora do ORM"
        verbose_name_plural = "Marcas de alteração fora do ORM"
        ordering = ["changed_at"]
        indexes = [
            models.Index(fields=["processed_at", "changed_at"]),
            models.Index(fields=["table_name", "row_id"]),
        ]

    def __str__(self):
        return f"{self.table_name}/{self.row_id} [{self.operation}]"
