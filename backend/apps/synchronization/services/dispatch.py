"""Monta os lotes que saem daqui e contabiliza o que voltou.

O dispatcher nunca apaga um evento: ele muda o estado. PENDING vira SENT, SENT
vira ACKNOWLEDGED quando o outro lado confirma, e uma falha vira FAILED com
data da próxima tentativa. Enquanto não for ACKNOWLEDGED o evento continua
aqui, com o payload inteiro — é essa a recuperação depois de uma semana sem
internet.
"""
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus
from apps.synchronization.services import crypto, retry

logger = logging.getLogger(__name__)

MAX_EVENTOS_PADRAO = 200
MAX_BYTES_PADRAO = 1_048_576  # 1 MiB por lote


def limites():
    return (
        int(getattr(settings, "SYNC_BATCH_MAX_EVENTS", MAX_EVENTOS_PADRAO)),
        int(getattr(settings, "SYNC_BATCH_MAX_BYTES", MAX_BYTES_PADRAO)),
    )


def collect_batch(source_node, target_node=None):
    """Próximo lote pronto para sair, respeitando quantidade e bytes.

    A ordem é sempre a da sequência: aplicar o item antes do pedido quebraria
    a chave estrangeira do outro lado.
    """
    from apps.synchronization.models import SyncEvent

    max_eventos, max_bytes = limites()
    # Com destino conhecido, a consulta é POR DESTINO: todo evento OUTBOUND
    # daqui foi criado por esta instalação, e amarrar ao `source_node` fazia o
    # lote sair vazio quando havia mais de um nó `is_self` (ver
    # `provisioning.ensure_self_node`).
    if target_node is not None:
        consulta = SyncEvent.objects.pending_for_target(target_node)
    else:
        consulta = SyncEvent.objects.pending_outbound(source_node)

    lote, bytes_acumulados = [], 0
    for evento in consulta[: max_eventos * 2]:
        tamanho = len(crypto.canonical_json(evento.payload))
        if lote and (len(lote) >= max_eventos or bytes_acumulados + tamanho > max_bytes):
            break
        lote.append(evento)
        bytes_acumulados += tamanho
    return lote, bytes_acumulados


def serialize_batch(eventos):
    """Os eventos no formato que viaja dentro do payload da mensagem."""
    return [
        {
            "event_id": str(evento.event_id),
            "account_id": str(evento.account_id),
            "target_node_id": str(evento.target_node_id),
            "sequence": evento.sequence,
            "entity_type": evento.entity_type,
            "entity_id": evento.entity_id,
            "operation": evento.operation,
            "entity_version": evento.entity_version,
            "protocol_version": evento.protocol_version,
            "payload": evento.payload,
            "payload_checksum": evento.payload_checksum,
            "correlation_id": str(evento.correlation_id) if evento.correlation_id else None,
        }
        for evento in eventos
    ]


def mark_sent(eventos):
    """SENT, não "enviado e esquecido": continua na fila de não confirmados."""
    from apps.synchronization.models import SyncEvent

    agora = timezone.now()
    ids = [e.pk for e in eventos]
    SyncEvent.objects.filter(pk__in=ids).update(status=EventStatus.SENT, sent_at=agora)
    return len(ids)


def mark_batch_failed(eventos, erro):
    """Falha no envio inteiro: cada evento ganha sua própria retentativa."""
    for evento in eventos:
        retry.mark_failure(evento, erro)
    return len(eventos)


def apply_ack(source_node, ack_payload, *, target_node=None):
    """Processa o ACK/NACK do outro lado.

    RECEIVED só avança o estado; ACKNOWLEDGED é o que encerra. Um evento
    listado como falho volta para a escada de retentativa em vez de sumir.

    `target_node` é o nó que a CONEXÃO autenticou, e quando ele vem, só os
    eventos endereçados a ele podem ser confirmados. Sem esse filtro, a única
    coisa entre uma loja e a fila de outra é adivinhar um `event_id` — e
    "confirmar" é justamente o poder de tirar um evento da fila para sempre.
    O UUID é impossível de adivinhar, então isto nunca foi uma porta aberta;
    é a diferença entre não ter fechadura e não ter endereço.

    Fica opcional porque o lado LOJA fala com um interlocutor só: lá a
    pergunta "de quem veio este ACK?" tem uma resposta possível.
    """
    from apps.synchronization.models import SyncEvent

    agora = timezone.now()
    confirmados = ack_payload.get("acknowledged") or []
    recebidos = ack_payload.get("received") or []
    falhos = ack_payload.get("failed") or []

    meus = SyncEvent.objects.filter(source_node=source_node, direction=Direction.OUTBOUND)
    if target_node is not None:
        meus = meus.filter(target_node=target_node)

    with transaction.atomic():
        if recebidos:
            meus.filter(event_id__in=recebidos).exclude(
                status=EventStatus.ACKNOWLEDGED
            ).update(status=EventStatus.RECEIVED, received_at=agora)
        if confirmados:
            meus.filter(event_id__in=confirmados).update(
                status=EventStatus.ACKNOWLEDGED, acknowledged_at=agora
            )
        for item in falhos:
            evento = meus.filter(event_id=item.get("event_id")).first()
            if evento is not None:
                retry.mark_failure(evento, item.get("error", "NACK sem detalhe"))

    return len(confirmados) + len(recebidos) + len(falhos)


def resend_unconfirmed(node):
    """Reconexão: o que saiu e ninguém confirmou volta para PENDING.

    O `event_id` é o mesmo, então reaplicar é impossível — o destino responde
    ACK sem tocar no domínio (§18).
    """
    from apps.synchronization.models import SyncEvent

    return (
        SyncEvent.objects.unconfirmed(node)
        .filter(status=EventStatus.SENT)
        .update(status=EventStatus.PENDING, next_attempt_at=None)
    )
