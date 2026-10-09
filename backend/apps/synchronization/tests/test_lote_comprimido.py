"""O lote viaja comprimido — e quem não sabe descomprimir não recebe compressão.

O payload saía cifrado e em base64: o JSON de centenas de eventos ia inteiro
pela internet da loja, e a compressão do WebSocket não ajudava, porque dado
cifrado não comprime. Comprimir ANTES de cifrar reduz o lote várias vezes.

Loja e nuvem atualizam em momentos diferentes. Cada lado só comprime quando o
outro anunciou no aperto de mão que sabe ler (`capabilities`).
"""
import json

import pytest

from apps.synchronization.constants import MessageType
from apps.synchronization.services import crypto, protocol

CHAVE = crypto.generate_key()


def _lote(n=200):
    return {"events": [
        {"event_id": f"ev-{i}", "entity_type": "order_item", "payload": {
            "fields": {"product_id": "p-1", "quantity": "1.000", "unit_price": "12.50",
                       "status": "pending", "notes": ""}}}
        for i in range(n)
    ]}


def _envelope(payload, **kwargs):
    return protocol.build(
        MessageType.EVENT_BATCH, source_node_id="a", target_node_id="b", account_id="c",
        payload=payload, key=CHAVE, key_id="k", **kwargs,
    )


def test_lote_comprimido_ida_e_volta():
    lote = _lote()
    envelope = _envelope(lote, comprimir=True)

    assert envelope["compression"] == "zlib"
    assert protocol.parse(envelope, CHAVE) == lote


def test_comprimido_e_bem_menor():
    lote = _lote()
    cheio = len(json.dumps(_envelope(lote)))
    comprimido = len(json.dumps(_envelope(lote, comprimir=True)))

    assert comprimido * 4 < cheio


def test_sem_compressao_continua_como_antes():
    """A versão antiga do outro lado manda sem `compression` e precisa ser lida."""
    lote = _lote(3)
    envelope = _envelope(lote)

    assert "compression" not in envelope or envelope["compression"] is None
    assert protocol.parse(envelope, CHAVE) == lote


def test_compressao_desconhecida_e_recusada():
    envelope = _envelope(_lote(1), comprimir=True)
    envelope["compression"] = "brotli"

    with pytest.raises(protocol.ProtocolError):
        protocol.parse(envelope, CHAVE)


def test_a_loja_anuncia_que_le_compressao():
    from apps.synchronization.services.transport import CloudConnection

    conexao = CloudConnection.__new__(CloudConnection)
    for campo in ("node_id", "pair_id", "account_id", "app_version"):
        setattr(conexao, campo, "x")

    assert "zlib" in conexao._hello_payload()["capabilities"]


def test_a_loja_so_comprime_se_a_nuvem_anunciou():
    from apps.synchronization.services.transport import CloudConnection

    conexao = CloudConnection.__new__(CloudConnection)
    conexao.comprimir = False
    conexao._ler_capacidades({"capabilities": []})
    assert conexao.comprimir is False

    conexao._ler_capacidades({"capabilities": ["zlib"]})
    assert conexao.comprimir is True


def test_mede_o_relogio_da_loja_contra_o_da_nuvem():
    """Com "vence o mais novo", relógio errado decide quem vence."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.synchronization.services import relogio

    agora = timezone.now()
    nuvem = (agora - timedelta(minutes=3)).isoformat()

    assert round(relogio.desvio_em_segundos(nuvem, agora)) == 180
    assert relogio.desvio_em_segundos("", agora) is None
    assert relogio.desvio_em_segundos("lixo", agora) is None
