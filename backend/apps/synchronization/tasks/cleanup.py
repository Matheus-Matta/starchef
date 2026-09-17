"""Retenção: apaga o que já foi confirmado, e nada além disso."""
import logging

from celery import shared_task
from django.conf import settings

from apps.synchronization.services import guard, recovery

logger = logging.getLogger(__name__)


@shared_task(name="sync.prune_acknowledged_events", queue="sync.cleanup")
def prune_acknowledged_events(dias=None):
    """Limpeza conservadora: só ACKNOWLEDGED e só depois da retenção.

    Um evento DEAD nunca é apagado por aqui. Ele é justamente o que alguém vai
    querer ler daqui a duas semanas.
    """
    if not guard.is_enabled():
        return 0

    retencao = dias or int(getattr(settings, "SYNC_RETENTION_DAYS", 30))
    apagados = recovery.prune(retencao)
    if apagados:
        logger.info("sync: %s evento(s) confirmados apagados (retenção %sd)", apagados, retencao)
    return apagados
