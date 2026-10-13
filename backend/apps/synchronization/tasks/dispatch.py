"""Aviso de disponibilidade da NUVEM para as lojas conectadas (§13.2)."""
import asyncio
import logging

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

from apps.core.rls import trabalho_de_plataforma
from apps.synchronization.constants import Direction, EventStatus, MessageType
from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import guard, nodes

logger = logging.getLogger(__name__)

#: Quanto um aviso pode esperar o Redis. Sem prazo, um `group_send` travado
#: segurava o processo do worker os 30 min do limite global, até o SIGKILL.
#: O aviso é só um "tem novidade": perdê-lo custa no máximo o próximo tique.
PRAZO_DO_AVISO = 5


def _avisar(camada, grupo):
    async def _enviar():
        await asyncio.wait_for(
            camada.group_send(grupo, {"type": "sync.available",
                                      "payload": {"message_type": MessageType.SYNC_AVAILABLE}}),
            timeout=PRAZO_DO_AVISO,
        )

    try:
        async_to_sync(_enviar)()
    except asyncio.TimeoutError:
        logger.warning("Aviso de sincronizacao para %s passou de %ss; fica para o proximo.",
                       grupo, PRAZO_DO_AVISO)
        return False
    return True


# Roda a cada 10 s: o limite é do tamanho dela, não os 30 min globais.
@shared_task(name="sync.notify_pending_to_local_nodes", queue="sync.dispatch",
             soft_time_limit=60, time_limit=90)
@trabalho_de_plataforma("avisa todas as lojas com fila pendente")
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
        if _avisar(camada, destino.group_name):
            avisados += 1
    return avisados
