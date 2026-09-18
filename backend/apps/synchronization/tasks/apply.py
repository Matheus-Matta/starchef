"""Aplicação dos eventos que já estão seguros na inbox."""
import logging

from celery import shared_task

from apps.core.rls import trabalho_de_plataforma
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import apply, guard, nodes

logger = logging.getLogger(__name__)

MAX_POR_EXECUCAO = 500


@shared_task(name="sync.apply_pending_events", queue="sync.apply")
@trabalho_de_plataforma("aplica a fila de entrada de todas as lojas")
def apply_pending_events(event_pks=None):
    """Aplica em ordem de sequência. Chamada pelo consumer e pelo beat.

    Roda igual nos dois nós: a nuvem aplica o que veio da loja, a loja aplica o
    que veio da nuvem. Quem impede o eco é o `applying_remote_event` lá dentro.
    """
    if not guard.is_enabled():
        return 0

    proprio = nodes.self_node_or_none()
    if proprio is None:
        return 0

    consulta = SyncEvent.objects.pending_inbound(proprio)
    if event_pks:
        consulta = consulta.filter(pk__in=event_pks)

    aplicados = 0
    for evento in consulta[:MAX_POR_EXECUCAO]:
        if apply.apply_event(evento):
            aplicados += 1
    if aplicados:
        logger.info("sync: %s evento(s) aplicados", aplicados)
    return aplicados
