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
            _guardar_na_quarentena(
                SyncEvent, bruto, connection_node, destino, account_id, run, erro
            )
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


def _guardar_na_quarentena(SyncEvent, bruto, origem, destino, account_id, run, erro):
    """O evento recusado FICA — como DEAD, com o motivo escrito.

    Antes ele era só descartado com uma linha de log, e isso escondeu um
    defeito por um dia inteiro: uma loja endereçava tudo para um nó que a
    nuvem havia apagado, e 729 eventos — pagamentos incluídos — foram para o
    ralo sem que a fila acusasse nada. `sync_status` dizia "0 mortos", o
    painel dizia que estava tudo bem, e o dado não chegava.

    DEAD é o estado certo e já existe: `pending_inbound` só olha RECEIVED e
    FAILED, então ele NUNCA é aplicado — a garantia de segurança continua
    inteira. O que muda é que ele passa a ser contado em "mortos", aparece no
    `sync_status` e nas métricas, e `sync_recover --requeue` consegue
    ressuscitá-lo depois que a causa for corrigida.
    """

    payload = bruto.get("payload") or {}
    if "bytes" in str(erro):
        # Foi recusado POR TAMANHO: guardar o payload seria guardar exatamente
        # o que não coube. O motivo já diz tudo o que se precisa saber.
        payload = {}
    try:
        with transaction.atomic():
            SyncEvent.objects.create(
                event_id=bruto["event_id"],
                account_id=account_id,
                source_node=origem,
                # O destino aqui é ESTE nó, não o que veio no envelope: o
                # endereço errado é justamente o motivo da recusa, e gravá-lo
                # criaria uma referência para um nó que pode nem existir.
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
                payload_checksum=bruto.get("payload_checksum") or "",
                status=EventStatus.DEAD,
                last_error=str(erro)[:2000],
                correlation_id=bruto.get("correlation_id") or None,
            )
    except IntegrityError:
        # `event_id` repetido: a origem reenviou o que já está em quarentena.
        # Um registro basta.
        pass


def mark_acknowledged(source_node, event_ids):
    """A origem confirmou que sabe que aplicamos. Fecha o ciclo."""
    from apps.synchronization.models import SyncEvent
    from django.utils import timezone

    return SyncEvent.objects.filter(
        source_node=source_node, event_id__in=event_ids, direction=Direction.OUTBOUND
    ).update(status=EventStatus.ACKNOWLEDGED, acknowledged_at=timezone.now())
