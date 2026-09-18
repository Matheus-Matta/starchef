"""Aviso de disponibilidade da NUVEM para as lojas conectadas (§13.2)."""
import logging

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

from apps.synchronization.constants import Direction, EventStatus, MessageType
from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import guard, nodes

logger = logging.getLogger(__name__)


@shared_task(name="sync.notify_pending_to_local_nodes", queue="sync.dispatch")
def notify_pending_to_local_nodes():
    """Avisa cada loja com fila pendente, no grupo exclusivo dela.

    O aviso vai SÓ para o grupo do nó de destino. Não existe broadcast global:
    é o que impede a conta A de saber que a conta B tem novidade.
    """
    if not guard.is_enabled() or not nodes.is_cloud():
        return 0

    proprio = nodes.self_node_or_none()
    if proprio is None:
        return 0

    # NÃO filtra por `source_node`, e isso é a correção de um defeito caro.
    # Todo evento OUTBOUND que existe aqui foi criado por esta instalação, então
    # a pergunta útil é "para quem vai". Amarrar ao `source_node` fazia o aviso
    # nunca sair quando a identidade da nuvem resolvia para outro registro — e
    # como a loja só pede depois de avisada, ela ficava conectada, autenticada e
    # calada, com centenas de eventos endereçados a ela e `tentativas=0`.
    pendentes = (
        SyncEvent.objects.filter(
            direction=Direction.OUTBOUND,
            status__in=[EventStatus.PENDING, EventStatus.FAILED],
        )
        .values_list("target_node_id", flat=True)
        .distinct()
    )

    camada = get_channel_layer()
    if camada is None:  # pragma: no cover
        return 0

    avisados = 0
    for target_id in pendentes:
        destino = SyncNode.objects.filter(pk=target_id).first()
        if destino is None or not destino.can_connect:
            continue
        async_to_sync(camada.group_send)(
            destino.group_name,
            {"type": "sync.available", "payload": {"message_type": MessageType.SYNC_AVAILABLE}},
        )
        avisados += 1
    return avisados
