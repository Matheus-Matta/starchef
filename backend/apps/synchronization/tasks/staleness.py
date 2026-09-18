"""Tarefa periódica: fila endereçada a nó que não responde tem prazo.

No dia a dia não acha nada, e é esse o resultado esperado — como a rede de
segurança das triggers. Ela existe para o dia em que uma loja rematricular e
deixar a carga inteira endereçada a uma ficha que ninguém mais usa.
"""
import logging

from celery import shared_task

from apps.synchronization.services import guard, staleness

logger = logging.getLogger(__name__)


@shared_task(name="sync.expire_stale_queues", queue="sync.cleanup")
def expire_stale_queues():
    if not guard.is_enabled():
        return {}
    return staleness.expirar_filas()
