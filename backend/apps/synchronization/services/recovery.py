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
    """Apaga SÓ o que o outro lado já confirmou, e só da fila de SAÍDA.

    A restrição a OUTBOUND não é detalhe de desempenho: a linha de ENTRADA é
    o índice de deduplicação. `inbox._gravar` decide se um evento já chegou
    perguntando se existe `event_id` igual — apagar a linha apaga a memória de
    que aquilo já foi aplicado, e um reenvio tardio volta a passar como novo.

    O cenário não é teórico. Basta o ACK se perder no caminho: a origem deixa
    o evento em SENT para sempre e `resend_unconfirmed` o reenvia na próxima
    reconexão, que pode ser meses depois. Aqui ele já tinha sido aplicado.

    Quem cuida do tamanho da fila de entrada é `tombstone_inbound`, que tira o
    payload e deixa a linha.
    """
    corte = timezone.now() - timezone.timedelta(days=dias)
    apagados, _ = SyncEvent.objects.filter(
        direction=Direction.OUTBOUND,
        status=EventStatus.ACKNOWLEDGED,
        acknowledged_at__lt=corte,
    ).delete()
    return apagados


def tombstone_inbound(dias=30):
    """Esvazia o payload dos eventos de ENTRADA já aplicados. Não apaga a linha.

    Sem isto a inbox cresce para sempre: nada nunca apagava um INBOUND, porque
    ele termina em APPLIED e a retenção só olhava para ACKNOWLEDGED. Numa loja
    movimentada são centenas de milhares de linhas carregando o JSON inteiro
    de cada venda que veio da nuvem, guardado só para que a deduplicação tenha
    o que consultar.

    Mas quem deduplica é o `event_id`, não o payload. Então a linha fica — com
    uns 200 bytes em vez de alguns KB — e a memória de "isto já foi aplicado"
    passa a durar mais que o conteúdo, que é exatamente a ordem correta: a
    retenção da deduplicação precisa ser MAIOR que a dos eventos, nunca menor.

    Só toca em APPLIED. Um DEAD continua inteiro: é dele que alguém precisa
    quando vai reprocessar à mão.
    """
    corte = timezone.now() - timezone.timedelta(days=dias)
    return (
        SyncEvent.objects.filter(
            direction=Direction.INBOUND,
            status=EventStatus.APPLIED,
            applied_at__lt=corte,
        )
        .exclude(payload={})
        .update(payload={})
    )


def discard_outbound(node):
    """Apaga a fila de SAÍDA de um nó e encerra as cargas dele.

    Devolve `(eventos_apagados, cargas_encerradas)`.

    Para que serve: a fila ficou apontando para o lugar errado — tipicamente
    uma loja que rematriculou e passou a conectar por outro nó, deixando
    centenas de eventos endereçados a um destino que ninguém mais escuta.
    Refazer a carga é mais limpo que reaproveitá-los: os eventos novos saem do
    estado ATUAL do banco, sem payload velho e sem sequência remendada.

    Só toca em OUTBOUND, e isso não é detalhe. Um evento INBOUND é dado que a
    loja mandou e que este lado ainda não aplicou — uma venda, um pagamento,
    uma sangria. Apagar isso perderia o dado de verdade, sem volta, e é a
    única coisa que este módulo existe para impedir.
    """
    from apps.synchronization.constants import Direction, RunStatus
    from apps.synchronization.models import SyncRun

    apagados, _ = SyncEvent.objects.filter(
        target_node=node, direction=Direction.OUTBOUND
    ).delete()

    cargas = SyncRun.objects.filter(target_node=node, status__in=list(RunStatus.BUSY))
    cancelados = cargas.update(
        status=RunStatus.CANCELLED,
        error="Fila descartada no Admin; refaça a carga.",
        completed_at=timezone.now(),
    )

    logger.warning(
        "sync: fila de saída do nó %s descartada — %s evento(s), %s carga(s)",
        node.id, apagados, cancelados,
    )
    return apagados, cancelados
