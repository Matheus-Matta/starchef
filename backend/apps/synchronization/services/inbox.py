"""Persistir ANTES de confirmar. É a regra que sustenta tudo (§10.3).

O destino só responde RECEIVED depois de autenticar, validar destino e conta,
conferir o checksum, decifrar, gravar e commitar. Se o processo morrer entre
o commit e o envio do ACK, a origem reenvia o mesmo `event_id` e a
deduplicação abaixo devolve o mesmo resultado sem duplicar nada.
"""
import logging

from django.db import IntegrityError, transaction

from apps.synchronization.constants import Direction, EventStatus
from apps.synchronization.services import crypto

logger = logging.getLogger(__name__)


class CrossTenantRejected(PermissionError):
    """Evento cuja conta ou destino não bate com a conexão autenticada."""


def store_batch(events_payload, *, connection_node, account_id, run=None):
    """Grava um lote na inbox e devolve `(aceitos, sequência_máxima)`.

    `connection_node` é o nó do OUTRO lado, o que a conexão autenticou. Nada
    do payload substitui essa identidade: é essa a diferença entre "o envelope
    diz que é da conta A" e "a conexão provou ser da conta A".
    """
    from apps.synchronization.models import SyncEvent
    from apps.synchronization.services import nodes

    destino = nodes.self_node()
    aceitos, maior_sequencia = [], 0

    with transaction.atomic():
        for bruto in events_payload:
            _validar_escopo(bruto, connection_node, destino, account_id)
            evento = _gravar(SyncEvent, bruto, connection_node, destino, account_id, run)
            if evento is not None:
                aceitos.append(evento)
            maior_sequencia = max(maior_sequencia, int(bruto.get("sequence") or 0))

    return aceitos, maior_sequencia


def _validar_escopo(bruto, connection_node, destino, account_id):
    """Cross-tenant é rejeitado e auditado — nunca aplicado (§9.2)."""
    alvo = str(bruto.get("target_node_id") or "")
    if alvo and alvo != str(destino.id):
        logger.error(
            "sync: target_node adulterado node=%s alvo=%s", connection_node.id, alvo
        )
        raise CrossTenantRejected("target_node do evento não é este nó.")

    conta_evento = str(bruto.get("account_id") or account_id)
    if conta_evento != str(account_id):
        logger.error(
            "sync: account_id adulterado node=%s conta=%s", connection_node.id, conta_evento
        )
        raise CrossTenantRejected("account_id do evento não é o da conexão autenticada.")


def _gravar(SyncEvent, bruto, origem, destino, account_id, run):
    """Insere o evento. `event_id` repetido devolve None — é a deduplicação."""
    payload = bruto.get("payload") or {}
    checksum_recebido = bruto.get("payload_checksum") or ""
    if checksum_recebido and crypto.checksum(payload) != checksum_recebido:
        raise ValueError(f"Checksum divergente no evento {bruto.get('event_id')}.")

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
