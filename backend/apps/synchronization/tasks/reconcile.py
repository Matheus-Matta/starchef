"""Reconciliação: comparar cursores e achar lacuna de sequência."""
import logging

from celery import shared_task

from apps.core.rls import trabalho_de_plataforma
from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus, NodeStatus
from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import dispatch, guard, nodes

logger = logging.getLogger(__name__)

#: Sem notícia por mais que isto, o nó é considerado offline.
SILENCIO_MINUTOS = 5


@shared_task(name="sync.reconcile_nodes", queue="sync.reconcile")
@trabalho_de_plataforma("reconciliacao entre todos os nos")
def reconcile_nodes():
    """Marca nós calados como OFFLINE e reenfileira o que ficou sem confirmação.

    É a rede de segurança para o caso em que a conexão morreu sem avisar: o
    socket some, ninguém recebe `disconnect`, e os eventos ficariam em SENT
    para sempre. Aqui eles voltam para PENDING — com o mesmo `event_id`, então
    reenviar é seguro.
    """
    if not guard.is_enabled():
        return {}

    corte = timezone.now() - timezone.timedelta(minutes=SILENCIO_MINUTOS)
    calados = SyncNode.objects.filter(
        status=NodeStatus.ACTIVE, last_seen_at__lt=corte
    )
    offline = calados.update(status=NodeStatus.OFFLINE)

    proprio = nodes.self_node_or_none()
    reenfileirados = 0
    if proprio is not None:
        reenfileirados = (
            SyncEvent.objects.filter(
                direction=Direction.OUTBOUND,
                source_node=proprio,
                status=EventStatus.SENT,
                sent_at__lt=corte,
            ).update(status=EventStatus.PENDING, next_attempt_at=None)
        )

    if offline or reenfileirados:
        logger.info("sync: %s nó(s) offline, %s evento(s) reenfileirados", offline, reenfileirados)
    return {"offline": offline, "reenfileirados": reenfileirados}


@shared_task(name="sync.resend_unconfirmed", queue="sync.reconcile")
@trabalho_de_plataforma("reconciliacao entre todos os nos")
def resend_unconfirmed():
    """Reenvia tudo que saiu e não voltou. Usada na reconexão e no Admin."""
    if not guard.is_enabled():
        return 0
    proprio = nodes.self_node_or_none()
    return dispatch.resend_unconfirmed(proprio) if proprio else 0
