"""Os passos síncronos (com banco) que o worker chama de dentro do laço async.

Ficam separados porque o laço é assíncrono e o ORM não é: cada função aqui é
um bloco que roda inteiro numa thread, via `sync_to_async`. Misturar os dois
no mesmo arquivo é o caminho mais curto para um `SynchronousOnlyOperation` em
produção.
"""
import logging

from apps.synchronization.constants import EventStatus
from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import apply, confirmacao, dispatch, inbox, nodes, relogio, retry

logger = logging.getLogger(__name__)

#: Teto de eventos aplicados por rodada: manter o laço responsivo importa mais
#: que esvaziar a fila numa tacada.
MAX_APLICAR = 200


def enviar_pendentes(_conexao):
    """Próximo lote da outbox, já serializado. `None` quando não há nada."""
    origem = nodes.self_node()
    lote, _bytes = dispatch.collect_batch(origem)
    if not lote:
        return None
    corpo = dispatch.serialize_batch(lote)
    return lote, corpo, lote[0].sequence, lote[-1].sequence


def registrar_lote_recebido(payload, peer_node_id):
    """Grava o lote na inbox ANTES de o worker responder qualquer coisa."""
    proprio = nodes.self_node()
    par = SyncNode.objects.filter(pk=peer_node_id).first() or nodes.peer_of(proprio)
    if par is None:
        raise RuntimeError("Lote recebido sem nó de origem conhecido.")

    aceitos, _maior, _recusados = inbox.store_batch(
        payload.get("events") or [],
        connection_node=par,
        account_id=proprio.account_id,
    )
    return [str(evento.pk) for evento in aceitos]


def aplicar_recebidos(ids=None):
    """Aplica em ordem de sequência. Devolve os `event_id` que entraram."""
    proprio = nodes.self_node()
    consulta = SyncEvent.objects.pending_inbound(proprio)
    if ids:
        consulta = consulta.filter(pk__in=ids)

    aplicados = []
    for evento in list(consulta[:MAX_APLICAR]):
        apply.apply_event(evento)
        evento.refresh_from_db(fields=["status"])
        if evento.status == EventStatus.APPLIED:
            aplicados.append(str(evento.event_id))
    if aplicados:
        _avancar_cursor(proprio, consulta)
        # O que acabou de entrar pode ser o pai que alguém esperava.
        retry.acordar_quem_espera_dependencia(proprio)
    return aplicados


def ao_reconectar():
    """Fecha a janela de queda e reenvia o que saiu sem confirmação.

    O lote transmitido no instante em que a rede caiu fica SENT para sempre —
    ou até `reconcile_nodes`, que só pega o que está assim há 5 minutos. A
    nuvem já reenfileira o dela no aperto de mão; a loja passa a fazer igual.
    Reenviar é seguro: o `event_id` é o mesmo e o destino ignora o que já viu.
    """
    nodes.registrar_reconexao()
    return dispatch.resend_unconfirmed(nodes.self_node())


def confirmacoes_pendentes(peer_node_id):
    """O que esta loja aplicou DEPOIS do lote e ainda não confirmou à nuvem."""
    proprio = nodes.self_node()
    par = SyncNode.objects.filter(pk=peer_node_id).first() or nodes.peer_of(proprio)
    return (par, confirmacao.aplicados_sem_confirmacao(par)) if par else (None, [])


def marcar_confirmados(par, event_ids):
    return confirmacao.marcar_confirmados(par, event_ids) if par else 0


def _avancar_cursor(proprio, consulta):
    ultimo = consulta.model.objects.filter(
        target_node=proprio, status__in=[EventStatus.APPLIED, EventStatus.ACKNOWLEDGED]
    ).order_by("-sequence").values_list("sequence", flat=True).first()
    if ultimo and ultimo > proprio.last_received_cursor:
        SyncNode.objects.filter(pk=proprio.pk).update(last_received_cursor=ultimo)


def tratar_ack(payload, peer_node_id):
    """Contabiliza a confirmação do outro lado na nossa outbox."""
    proprio = nodes.self_node()
    dispatch.apply_ack(proprio, payload)
    if peer_node_id:
        inbox.mark_acknowledged(proprio, payload.get("acknowledged") or [])
    return True


def estado_da_fila():
    """Números que o worker registra no log e o Admin mostra."""
    proprio = nodes.self_node_or_none()
    if proprio is None:
        return {"configurado": False}
    return {
        "configurado": True,
        "node_id": str(proprio.id),
        "pendentes": SyncEvent.objects.pending_outbound(proprio).count(),
        "nao_confirmados": SyncEvent.objects.unconfirmed(proprio).count(),
        "a_aplicar": SyncEvent.objects.pending_inbound(proprio).count(),
        "mortos": SyncEvent.objects.filter(status=EventStatus.DEAD).count(),
        "cursor_enviado": proprio.last_sent_cursor,
        "cursor_recebido": proprio.last_received_cursor,
        "desvio_do_relogio_s": relogio.desvio_conhecido(),
    }
