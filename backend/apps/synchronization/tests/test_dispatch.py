"""Lotes, confirmações e reenvio — o contador de "nada se perde"."""
import pytest

from apps.restaurants.models import Restaurant
from apps.synchronization.constants import Direction, EventStatus
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import dispatch

pytestmark = pytest.mark.django_db


def _restaurantes(conta, quantos=5):
    return [
        Restaurant.objects.create(account=conta, legal_name=f"L{i} LTDA", trade_name=f"L{i}")
        for i in range(quantos)
    ]


def test_lote_sai_em_ordem_de_sequencia(como_nuvem, conta, no_nuvem, no_loja):
    _restaurantes(conta, 3)
    lote, _bytes = dispatch.collect_batch(no_nuvem, no_loja)

    assert lote, "deveria haver eventos pendentes"
    sequencias = [e.sequence for e in lote]
    assert sequencias == sorted(sequencias)


def test_teto_de_quantidade_corta_o_lote(como_nuvem, conta, no_nuvem, no_loja, settings):
    settings.SYNC_BATCH_MAX_EVENTS = 2
    _restaurantes(conta, 5)
    lote, _bytes = dispatch.collect_batch(no_nuvem, no_loja)
    assert len(lote) == 2


def test_teto_de_bytes_corta_o_lote(como_nuvem, conta, no_nuvem, no_loja, settings):
    """Um pedido com cem itens não pode virar uma mensagem de 20 MB."""
    settings.SYNC_BATCH_MAX_EVENTS = 1000
    settings.SYNC_BATCH_MAX_BYTES = 1  # força o corte no primeiro
    _restaurantes(conta, 4)
    lote, _bytes = dispatch.collect_batch(no_nuvem, no_loja)
    assert len(lote) == 1


def test_enviado_continua_na_fila_de_nao_confirmados(como_nuvem, conta, no_nuvem, no_loja):
    """SENT não é "enviado e esquecido"."""
    _restaurantes(conta, 2)
    lote, _ = dispatch.collect_batch(no_nuvem, no_loja)
    dispatch.mark_sent(lote)

    assert SyncEvent.objects.unconfirmed(no_nuvem).count() == len(lote)
    # E já não aparece como pendente de envio.
    assert not SyncEvent.objects.pending_outbound(no_nuvem).filter(
        pk__in=[e.pk for e in lote]
    ).exists()


def test_ack_encerra_o_ciclo(como_nuvem, conta, no_nuvem, no_loja):
    _restaurantes(conta, 2)
    lote, _ = dispatch.collect_batch(no_nuvem, no_loja)
    dispatch.mark_sent(lote)

    dispatch.apply_ack(no_nuvem, {"acknowledged": [str(e.event_id) for e in lote]})
    for evento in lote:
        evento.refresh_from_db()
        assert evento.status == EventStatus.ACKNOWLEDGED
        assert evento.acknowledged_at is not None


def test_nack_devolve_para_a_escada_de_retentativa(como_nuvem, conta, no_nuvem, no_loja):
    _restaurantes(conta, 1)
    lote, _ = dispatch.collect_batch(no_nuvem, no_loja)
    dispatch.mark_sent(lote)

    dispatch.apply_ack(no_nuvem, {
        "failed": [{"event_id": str(lote[0].event_id), "error": "banco do destino fora"}]
    })
    lote[0].refresh_from_db()
    assert lote[0].status == EventStatus.FAILED
    assert lote[0].attempts == 1
    assert lote[0].next_attempt_at is not None
    assert "banco do destino fora" in lote[0].last_error


def test_received_nao_encerra_nada(como_nuvem, conta, no_nuvem, no_loja):
    """RECEIVED só diz "chegou". Encerrar é ACKNOWLEDGED."""
    _restaurantes(conta, 1)
    lote, _ = dispatch.collect_batch(no_nuvem, no_loja)
    dispatch.mark_sent(lote)

    dispatch.apply_ack(no_nuvem, {"received": [str(lote[0].event_id)]})
    lote[0].refresh_from_db()
    assert lote[0].status == EventStatus.RECEIVED
    assert lote[0].acknowledged_at is None


def test_reconexao_reenvia_o_que_ficou_sem_confirmacao(como_nuvem, conta, no_nuvem, no_loja):
    _restaurantes(conta, 3)
    lote, _ = dispatch.collect_batch(no_nuvem, no_loja)
    dispatch.mark_sent(lote)

    devolvidos = dispatch.resend_unconfirmed(no_nuvem)
    assert devolvidos == len(lote)
    for evento in lote:
        evento.refresh_from_db()
        assert evento.status == EventStatus.PENDING


def test_ja_confirmado_nao_volta_no_reenvio(como_nuvem, conta, no_nuvem, no_loja):
    _restaurantes(conta, 2)
    lote, _ = dispatch.collect_batch(no_nuvem, no_loja)
    dispatch.mark_sent(lote)
    dispatch.apply_ack(no_nuvem, {"acknowledged": [str(lote[0].event_id)]})

    dispatch.resend_unconfirmed(no_nuvem)
    lote[0].refresh_from_db()
    assert lote[0].status == EventStatus.ACKNOWLEDGED  # continua fechado


def test_lote_serializado_leva_o_que_o_destino_precisa(como_nuvem, conta, no_nuvem, no_loja):
    _restaurantes(conta, 1)
    lote, _ = dispatch.collect_batch(no_nuvem, no_loja)
    corpo = dispatch.serialize_batch(lote)

    assert len(corpo) == len(lote)
    item = corpo[0]
    for campo in ("event_id", "account_id", "target_node_id", "sequence",
                  "entity_type", "entity_id", "operation", "payload", "payload_checksum"):
        assert campo in item, f"falta {campo} no lote serializado"


def test_falha_no_envio_conta_para_cada_evento(como_nuvem, conta, no_nuvem, no_loja):
    _restaurantes(conta, 3)
    lote, _ = dispatch.collect_batch(no_nuvem, no_loja)

    assert dispatch.mark_batch_failed(lote, "conexão caiu no meio") == len(lote)
    for evento in lote:
        evento.refresh_from_db()
        assert evento.status == EventStatus.FAILED
        assert evento.attempts == 1


def test_fila_vazia_devolve_lote_vazio(como_nuvem, no_nuvem, no_loja):
    SyncEvent.objects.filter(direction=Direction.OUTBOUND).delete()
    lote, tamanho = dispatch.collect_batch(no_nuvem, no_loja)
    assert lote == [] and tamanho == 0
