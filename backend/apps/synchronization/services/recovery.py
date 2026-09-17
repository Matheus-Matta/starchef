"""Recuperar o que não foi enviado. A parte que só importa no pior dia.

A promessa do sistema é que um evento gravado não se perde. Isso exige três
coisas, e as três estão aqui:

1. **Ele continua no banco.** Nada é apagado antes da retenção — nem o que
   virou DEAD depois de doze tentativas. O payload inteiro fica gravado.
2. **Dá para olhar.** `snapshot()` e `stuck()` respondem "o que está parado,
   desde quando e por quê" sem ninguém precisar abrir o psql.
3. **Dá para trazer de volta.** `requeue()` devolve eventos à fila e
   `export()` grava o conteúdo em JSON, para o caso em que nem a fila resolve
   e alguém vai precisar reconstruir o registro à mão.

A retenção só apaga o que JÁ foi confirmado pelo outro lado (§18).
"""
import json
import logging

from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import retry

logger = logging.getLogger(__name__)

#: Parado há mais que isto sem confirmação = alguém precisa olhar.
LIMITE_PARADO_MINUTOS = 30


def snapshot(node=None, account_id=None):
    """Retrato da fila: quantos, em que estado, e o mais antigo de cada um."""
    consulta = SyncEvent.objects.all()
    if node is not None:
        consulta = consulta.filter(source_node=node) | consulta.filter(target_node=node)
    if account_id:
        consulta = consulta.filter(account_id=account_id)

    por_estado = {}
    for estado, _rotulo in EventStatus.CHOICES:
        do_estado = consulta.filter(status=estado)
        quantidade = do_estado.count()
        if not quantidade:
            continue
        mais_antigo = do_estado.order_by("created_at").values_list("created_at", flat=True).first()
        por_estado[estado] = {"total": quantidade, "mais_antigo": mais_antigo}

    return {
        "total": consulta.count(),
        "por_estado": por_estado,
        "nao_enviados": consulta.filter(
            direction=Direction.OUTBOUND, status__in=list(EventStatus.OUTBOUND_OPEN)
        ).count(),
        "nao_aplicados": consulta.filter(
            direction=Direction.INBOUND, status__in=list(EventStatus.INBOUND_OPEN)
        ).count(),
        "mortos": consulta.filter(status=EventStatus.DEAD).count(),
    }


def stuck(minutos=LIMITE_PARADO_MINUTOS, limite=100):
    """Eventos parados tempo demais — o que o alerta de "fila crescendo" olha."""
    corte = timezone.now() - timezone.timedelta(minutes=minutos)
    return list(
        SyncEvent.objects.filter(created_at__lt=corte)
        .exclude(status__in=list(EventStatus.TERMINAL))
        .exclude(status=EventStatus.APPLIED)
        .order_by("created_at")[:limite]
    )


def dead_letters(account_id=None, limite=500):
    """Os que desistiram. Continuam íntegros: payload, erro e tentativas."""
    consulta = SyncEvent.objects.filter(status=EventStatus.DEAD)
    if account_id:
        consulta = consulta.filter(account_id=account_id)
    return list(consulta.order_by("created_at")[:limite])


def requeue(eventos=None, *, account_id=None, entity_type=None, apenas_mortos=True):
    """Devolve eventos à fila, zerando a escada de retentativa.

    É o "Reprocessar falhas" do Admin e o `sync_recover --requeue` do terminal.
    Não reaplica nada sozinho: só recoloca na fila, e o `event_id` garante que
    o destino não vai duplicar.
    """
    if eventos is None:
        consulta = SyncEvent.objects.all()
        if apenas_mortos:
            consulta = consulta.filter(status=EventStatus.DEAD)
        else:
            consulta = consulta.filter(status__in=[EventStatus.DEAD, EventStatus.FAILED])
        if account_id:
            consulta = consulta.filter(account_id=account_id)
        if entity_type:
            consulta = consulta.filter(entity_type=entity_type)
        eventos = list(consulta)

    for evento in eventos:
        retry.revive(evento)
    logger.info("sync: %s evento(s) devolvidos à fila", len(eventos))
    return len(eventos)


def export(eventos, destino):
    """Grava os eventos em JSON — o resgate manual de último recurso."""
    dados = [
        {
            "event_id": str(evento.event_id),
            "account_id": str(evento.account_id),
            "direction": evento.direction,
            "sequence": evento.sequence,
            "entity_type": evento.entity_type,
            "entity_id": evento.entity_id,
            "operation": evento.operation,
            "entity_version": evento.entity_version,
            "status": evento.status,
            "attempts": evento.attempts,
            "last_error": evento.last_error,
            "created_at": evento.created_at.isoformat() if evento.created_at else None,
            "payload": evento.payload,
        }
        for evento in eventos
    ]
    with open(destino, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2, default=str)
    return len(dados)


def prune(dias=30):
    """Apaga SÓ o que o outro lado já confirmou. O resto fica, sempre."""
    corte = timezone.now() - timezone.timedelta(days=dias)
    apagados, _ = SyncEvent.objects.filter(
        status=EventStatus.ACKNOWLEDGED, acknowledged_at__lt=corte
    ).delete()
    return apagados
