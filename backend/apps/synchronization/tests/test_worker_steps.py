"""Os passos com banco que o laço do worker executa."""
import uuid

import pytest

from apps.restaurants.models import Restaurant
from apps.synchronization.constants import Direction, EventStatus
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import crypto, dispatch
from apps.synchronization import worker_steps

pytestmark = pytest.mark.django_db


def _bruto(conta, destino, *, sequence=1, entity_id=None):
    payload = {
        "schema_version": 1, "entity_type": "restaurant",
        "entity_id": str(entity_id or uuid.uuid4()), "entity_version": 10,
        "origin_node_id": str(uuid.uuid4()),
        "fields": {"account_id": str(conta.id), "legal_name": "W LTDA",
                   "trade_name": "W", "is_active": True},
    }
    return {
        "event_id": str(uuid.uuid4()),
        "account_id": str(conta.id),
        "target_node_id": str(destino.id),
        "sequence": sequence,
        "entity_type": "restaurant",
        "entity_id": payload["entity_id"],
        "operation": "UPSERT",
        "entity_version": 10,
        "payload": payload,
        "payload_checksum": crypto.checksum(payload),
    }


def test_sem_pendente_nao_ha_lote(como_loja, no_loja):
    SyncEvent.objects.filter(direction=Direction.OUTBOUND).delete()
    assert worker_steps.enviar_pendentes(None) is None


def test_lote_pronto_traz_corpo_e_sequencias(como_loja, conta, no_loja, no_nuvem):
    Restaurant.objects.create(account=conta, legal_name="E LTDA", trade_name="E")
    resultado = worker_steps.enviar_pendentes(None)

    assert resultado is not None
    lote, corpo, primeiro, ultimo = resultado
    assert len(lote) == len(corpo)
    assert primeiro == lote[0].sequence and ultimo == lote[-1].sequence


def test_lote_recebido_entra_na_inbox(como_loja, conta, no_loja, no_nuvem):
    ids = worker_steps.registrar_lote_recebido(
        {"events": [_bruto(conta, no_loja)]}, str(no_nuvem.id)
    )
    assert len(ids) == 1
    evento = SyncEvent.objects.get(pk=ids[0])
    assert evento.direction == Direction.INBOUND
    assert evento.status == EventStatus.RECEIVED


def test_peer_e_achado_pelo_pair_id_quando_o_id_nao_bate(como_loja, conta, no_loja, no_nuvem):
    """Sem `peer` explícito, o par é achado pelo `pair_id` compartilhado."""
    no_loja.peer = None
    no_loja.save(update_fields=["peer"])

    ids = worker_steps.registrar_lote_recebido(
        {"events": [_bruto(conta, no_loja)]}, str(uuid.uuid4())
    )
    assert len(ids) == 1


def test_lote_sem_origem_nenhuma_e_recusado(como_loja, conta, no_loja):
    """Sem peer e sem ninguém no mesmo pair_id, não há origem que valha."""
    no_loja.peer = None
    no_loja.pair_id = uuid.uuid4()  # órfão: ninguém compartilha este par
    no_loja.save(update_fields=["peer", "pair_id"])

    with pytest.raises(RuntimeError, match="sem nó de origem"):
        worker_steps.registrar_lote_recebido(
            {"events": [_bruto(conta, no_loja)]}, str(uuid.uuid4())
        )


def test_aplicar_recebidos_devolve_os_que_entraram(como_loja, conta, no_loja, no_nuvem):
    ids = worker_steps.registrar_lote_recebido(
        {"events": [_bruto(conta, no_loja)]}, str(no_nuvem.id)
    )
    aplicados = worker_steps.aplicar_recebidos(ids)

    assert len(aplicados) == 1
    assert Restaurant.all_objects.filter(trade_name="W").exists()


def test_aplicar_avanca_o_cursor_recebido(como_loja, conta, no_loja, no_nuvem):
    ids = worker_steps.registrar_lote_recebido(
        {"events": [_bruto(conta, no_loja, sequence=42)]}, str(no_nuvem.id)
    )
    worker_steps.aplicar_recebidos(ids)

    no_loja.refresh_from_db()
    assert no_loja.last_received_cursor == 42


def test_tratar_ack_fecha_o_evento_na_outbox(como_loja, conta, no_loja, no_nuvem):
    Restaurant.objects.create(account=conta, legal_name="A LTDA", trade_name="A")
    lote, _ = dispatch.collect_batch(no_loja)
    dispatch.mark_sent(lote)

    worker_steps.tratar_ack(
        {"acknowledged": [str(e.event_id) for e in lote]}, str(no_nuvem.id)
    )
    lote[0].refresh_from_db()
    assert lote[0].status == EventStatus.ACKNOWLEDGED


def test_estado_da_fila_resume_os_numeros(como_loja, conta, no_loja):
    Restaurant.objects.create(account=conta, legal_name="F LTDA", trade_name="F")
    estado = worker_steps.estado_da_fila()

    assert estado["configurado"] is True
    assert estado["node_id"] == str(no_loja.id)
    for chave in ("pendentes", "nao_confirmados", "a_aplicar", "mortos",
                  "cursor_enviado", "cursor_recebido"):
        assert chave in estado
    assert estado["pendentes"] >= 1


def test_estado_sem_no_configurado_diz_que_nao_esta(settings, conta):
    from apps.synchronization.services import nodes

    settings.SYNC_NODE_ID = ""
    nodes.invalidate_cache()
    assert worker_steps.estado_da_fila() == {"configurado": False}


def test_teto_de_aplicacao_por_rodada(como_loja, conta, no_loja, no_nuvem, monkeypatch):
    """O laço tem de continuar respondendo, não esvaziar tudo de uma vez."""
    monkeypatch.setattr(worker_steps, "MAX_APLICAR", 2)
    brutos = [_bruto(conta, no_loja, sequence=i) for i in range(1, 6)]
    ids = worker_steps.registrar_lote_recebido({"events": brutos}, str(no_nuvem.id))

    assert len(ids) == 5
    assert len(worker_steps.aplicar_recebidos()) <= 2
