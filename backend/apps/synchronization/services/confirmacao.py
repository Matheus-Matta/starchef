"""Confirmar à origem o que foi aplicado aqui DEPOIS da chegada do lote.

O "apliquei" (ACK `acknowledged`) saía só para o que entrava na hora em que o
lote chegava. O evento que esperou o pai e foi aplicado numa retentativa nunca
era confirmado, e na origem ficava RECEIVED para sempre: fila que não zera no
painel, limpeza que nunca apaga.

Cada lado agora varre, de tempos em tempos, o que aplicou e ainda não
confirmou, manda o ACK e marca o evento de entrada como ACKNOWLEDGED — o
estado que diz "a origem já sabe".
"""
from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus

LIMITE = 500


def aplicados_sem_confirmacao(origem, limite=LIMITE):
    """`event_id` das entradas vindas de `origem`, aplicadas e não confirmadas."""
    from apps.synchronization.models import SyncEvent

    return [str(i) for i in SyncEvent.objects.filter(
        direction=Direction.INBOUND, source_node=origem, status=EventStatus.APPLIED,
    ).order_by("sequence").values_list("event_id", flat=True)[:limite]]


def marcar_confirmados(origem, event_ids):
    from apps.synchronization.models import SyncEvent

    if not event_ids:
        return 0
    return SyncEvent.objects.filter(
        direction=Direction.INBOUND, source_node=origem, event_id__in=event_ids,
        status=EventStatus.APPLIED,
    ).update(status=EventStatus.ACKNOWLEDGED, acknowledged_at=timezone.now())
