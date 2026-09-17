"""Recolhe o que a trigger anotou e transforma em evento."""
import logging

from celery import shared_task

from apps.synchronization.services import dirty, guard

logger = logging.getLogger(__name__)


@shared_task(name="sync.collect_dirty_rows", queue="sync.dispatch")
def collect_dirty_rows():
    """A rede de segurança do §11.2, rodando a cada poucos segundos.

    Só faz algo quando alguém escreveu por fora do ORM. No dia a dia ela não
    encontra nada — e é exatamente esse o resultado esperado.
    """
    if not guard.is_enabled():
        return {"convertidas": 0, "ignoradas": 0}

    convertidas, ignoradas = dirty.process()
    return {"convertidas": convertidas, "ignoradas": ignoradas}


@shared_task(name="sync.prune_dirty_rows", queue="sync.cleanup")
def prune_dirty_rows(dias=7):
    """Marcas já processadas: uma por linha escrita, então acumulam rápido."""
    if not guard.is_enabled():
        return 0
    return dirty.prune(dias)
