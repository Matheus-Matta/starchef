"""Persistir ANTES de confirmar. É a regra que sustenta tudo (§10.3).

O destino só responde RECEIVED depois de autenticar, validar destino e conta,
conferir o checksum, decifrar, gravar e commitar. Se o processo morrer entre
o commit e o envio do ACK, a origem reenvia o mesmo `event_id` e a
deduplicação abaixo devolve o mesmo resultado sem duplicar nada.

O que pode entrar está em `inbox_guards.py`; aqui é como se grava.
"""
import logging

from django.db import IntegrityError, transaction

from apps.synchronization.constants import Direction, EventStatus
from apps.synchronization.services import crypto
from apps.synchronization.services.inbox_guards import (  # noqa: F401 — API do módulo
    FOLGA,
    BatchRejected,
    CrossTenantRejected,
    EventQuarantined,
    _limites,
    _validar_escopo,
    _validar_lote,
    _validar_tamanho,
)

logger = logging.getLogger(__name__)


def store_batch(events_payload, *, connection_node, account_id, run=None):
    """Grava um lote na inbox e devolve `(aceitos, sequência_máxima)`.

    `connection_node` é o nó do OUTRO lado, o que a conexão autenticou. Nada
    do payload substitui essa identidade: é essa a diferença entre "o envelope
    diz que é da conta A" e "a conexão provou ser da conta A".
    """
    from apps.synchronization.models import SyncEvent
    from apps.synchronization.services import nodes

    destino = nodes.self_node()
    _validar_lote(events_payload, connection_node)
    aceitos, recusados, maior_sequencia = [], [], 0

    for bruto in events_payload:
        # UM SAVEPOINT POR EVENTO. É o que impede o bloqueio de cabeça de fila.
        #
        # O lote inteiro vinha numa transação só, e qualquer evento estragado
        # derrubava todos: nada era gravado, a origem não recebia confirmação,
        # reenviava o MESMO lote, e batia no mesmo evento. Para sempre — e
        # tudo que vinha atrás dele nunca chegava.
        try:
            with transaction.atomic():
                _validar_escopo(bruto, connection_node, destino, account_id)
                _validar_tamanho(bruto, connection_node)
                evento = _gravar(
                    SyncEvent, bruto, connection_node, destino, account_id, run
                )
        except EventQuarantined as erro:
            recusados.append({"event_id": bruto.get("event_id"), "error": str(erro)})
            logger.error(
                "sync: evento %s em quarentena (nó %s) — %s",
                bruto.get("event_id"), connection_node.id, erro,
            )
            maior_sequencia = max(maior_sequencia, int(bruto.get("sequence") or 0))
            continue
        if evento is not None:
            aceitos.append(evento)
        maior_sequencia = max(maior_sequencia, int(bruto.get("sequence") or 0))

    return aceitos, maior_sequencia, recusados



def _gravar(SyncEvent, bruto, origem, destino, account_id, run):
    """Insere o evento. `event_id` repetido devolve None — é a deduplicação."""
    payload = bruto.get("payload") or {}
    checksum_recebido = bruto.get("payload_checksum") or ""
    if checksum_recebido and crypto.checksum(payload) != checksum_recebido:
        # Determinístico: a origem calcula do mesmo payload, então reenviar dá
        # o mesmo resultado. Insistir só reviveria o laço.
        raise EventQuarantined(
            f"Checksum divergente no evento {bruto.get('event_id')}."
        )

    existente = SyncEvent.objects.filter(event_id=bruto["event_id"]).first()
    if existente is not None:
        return None

    try:
        with transaction.atomic():
            return SyncEvent.objects.create(
                event_id=bruto["event_id"],
                account_id=account_id,
                source_node=origem,
                target_node=destino,
                run=run,
                direction=Direction.INBOUND,
                sequence=int(bruto.get("sequence") or 0),
                entity_type=bruto.get("entity_type", ""),
                entity_id=str(bruto.get("entity_id") or ""),
                operation=bruto.get("operation", ""),
                entity_version=int(bruto.get("entity_version") or 1),
                protocol_version=int(bruto.get("protocol_version") or 1),
                schema_version=int(payload.get("schema_version") or 1),
                payload=payload,
                payload_checksum=checksum_recebido or crypto.checksum(payload),
                status=EventStatus.RECEIVED,
                correlation_id=bruto.get("correlation_id") or None,
            )
    except IntegrityError:
        # Corrida entre dois workers no mesmo lote: o outro já gravou.
        return None


def mark_acknowledged(source_node, event_ids):
    """A origem confirmou que sabe que aplicamos. Fecha o ciclo."""
    from apps.synchronization.models import SyncEvent
    from django.utils import timezone

    return SyncEvent.objects.filter(
        source_node=source_node, event_id__in=event_ids, direction=Direction.OUTBOUND
    ).update(status=EventStatus.ACKNOWLEDGED, acknowledged_at=timezone.now())
