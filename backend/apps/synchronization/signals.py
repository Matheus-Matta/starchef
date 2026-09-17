"""Captura automática das gravações que passam pelo ORM.

Signals **não pegam tudo** — `QuerySet.update`, `bulk_create`, `bulk_update` e
SQL direto passam por fora, e o plano diz isso com todas as letras (§11.2). O
desenho aqui assume esse limite em vez de fingir que ele não existe:

- o caminho normal (`.save()` / `.delete()` de um service) é capturado aqui;
- o caminho em massa é responsabilidade de quem escreve o service, chamando
  `outbox.record()` dentro da mesma transação;
- e a rede de segurança é a carga total do Admin, que reconstrói o destino a
  partir do estado real do banco quando alguma coisa escapou.

Uma falha na captura NUNCA derruba a gravação do dado de negócio. A venda
acontece; o evento, se falhar, vira log e a carga total conserta depois.
"""
import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.synchronization.constants import Operation
from apps.synchronization.services import guard, outbox
from apps.synchronization.services.registry import registry

logger = logging.getLogger(__name__)


@receiver(post_save)
def capturar_gravacao(sender, instance, created, **kwargs):
    if not _sincronizavel(sender):
        return
    _registrar(instance, Operation.CREATE if created else Operation.UPDATE)


@receiver(post_delete)
def capturar_exclusao(sender, instance, **kwargs):
    if not _sincronizavel(sender):
        return
    _registrar(instance, Operation.DELETE)


def _sincronizavel(sender):
    if not guard.is_enabled() or outbox.is_applying():
        return False

    entrada = registry.for_model(sender)
    if entrada is None:
        return False

    # Durante o `migrate`, o Django entrega models HISTÓRICOS (do módulo
    # `__fake__`), reconstruídos a partir do estado das migrations. Eles têm o
    # mesmo app_label e o mesmo nome do model real, então casam com o catálogo
    # — e uma migration que popula permissões dispararia a captura de outbox.
    #
    # Isso quebrava o deploy do zero no PostgreSQL: a captura consulta a tabela
    # `SyncNode`, que naquele ponto do `migrate` ainda não existe. A consulta
    # falha, e no PostgreSQL uma consulta falha aborta a TRANSAÇÃO INTEIRA —
    # a migration seguinte morre com "current transaction is aborted".
    # (No SQLite isso passava batido: lá o erro não contamina a transação.)
    #
    # Comparar com a classe real resolve: model histórico nunca é ela.
    return entrada.model is sender


def _registrar(instance, operation):
    try:
        outbox.record(instance, operation=operation)
    except Exception:  # noqa: BLE001 — ver o docstring do módulo
        logger.exception(
            "sync: falha ao registrar evento de %s %s", type(instance).__name__, instance.pk
        )
