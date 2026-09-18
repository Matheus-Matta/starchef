"""Reprocessamento do que falhou, no ritmo da escada de backoff."""
import logging

from celery import shared_task

from apps.core.rls import trabalho_de_plataforma
from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import guard, nodes

logger = logging.getLogger(__name__)


@shared_task(name="sync.retry_failed_events", queue="sync.retry")
@trabalho_de_plataforma("reagenda falhas de todas as contas")
def retry_failed_events():
    """Devolve à fila o que já cumpriu o tempo de espera.

    Não reenvia nada sozinha: apenas marca PENDING, e quem envia continua sendo
    o worker da conexão. Assim não há dois caminhos concorrendo pelo mesmo
    evento.
    """
    if not guard.is_enabled():
        return 0

    proprio = nodes.self_node_or_none()
    if proprio is None:
        return 0

    prontos = SyncEvent.objects.filter(
        status=EventStatus.FAILED,
        next_attempt_at__lte=timezone.now(),
    )
    reentrada = prontos.filter(direction=Direction.OUTBOUND, source_node=proprio).update(
        status=EventStatus.PENDING
    )
    reaplicacao = prontos.filter(direction=Direction.INBOUND, target_node=proprio).update(
        status=EventStatus.RECEIVED
    )
    total = reentrada + reaplicacao
    if total:
        logger.info("sync: %s evento(s) voltaram para a fila", total)
    return total
