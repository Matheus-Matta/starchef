"""O consumer WSS da nuvem: handshake, escopo por conta e lotes.

O consumer é assíncrono e o ORM não é; estes testes são o que garante que a
ponte entre os dois está certa — um `SynchronousOnlyOperation` aqui só
apareceria em produção, com a loja já conectada.
"""
import json
import uuid

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from apps.synchronization.constants import (
    PROTOCOL_VERSION,
    CloseCode,
    Direction,
    MessageType,
    NodeStatus,
)
from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import crypto, protocol
from apps.synchronization.tests.conftest import CHAVE_DE_TESTE, TOKEN_DE_TESTE
from config.asgi import application

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

ROTA = "/ws/sync/v1/"


def _comunicador(token=TOKEN_DE_TESTE):
    cabecalhos = [(b"authorization", f"Bearer {token}".encode())]
    return WebsocketCommunicator(application, ROTA, headers=cabecalhos)


def _hello(no, **extra):
    base = {
        "node_id": str(no.id), "pair_id": str(no.pair_id), "account_id": str(no.account_id),
        "environment": no.environment, "protocol_version": PROTOCOL_VERSION,
        "schema_version": 1, "app_version": "3.0.0",
    }
    base.update(extra)
    return protocol.build(
        MessageType.HELLO, source_node_id=no.id, target_node_id=None,
        account_id=no.account_id, payload=base,
    )


async def _conectado(no, token=TOKEN_DE_TESTE):
    com = _comunicador(token)
    conectado, _ = await com.connect()
    assert conectado
    await com.send_to(text_data=json.dumps(_hello(no), default=str))
    return com


async def _ler(com, timeout=5):
    """Lê uma mensagem e devolve `(tipo, payload)` já decifrado.

    O consumer CIFRA as respostas com a chave do ambiente — ler `["payload"]`
    direto só funcionaria no modo em claro, que existe para depuração.
    """
    envelope = json.loads(await com.receive_from(timeout=timeout))
    tipo = envelope.get("message_type")
    if tipo == MessageType.ERROR:
        return tipo, envelope.get("payload", {})
    return tipo, protocol.parse(envelope, CHAVE_DE_TESTE)


async def _esperar_fechamento(com):
    saida = await com.receive_output(timeout=5)
    while saida["type"] != "websocket.close":
        saida = await com.receive_output(timeout=5)
    return saida["code"]


async def test_hello_valido_autentica(como_nuvem, no_loja):
    com = await _conectado(no_loja)
    tipo, payload = await _ler(com)

    assert tipo == MessageType.AUTHENTICATED
    assert payload["node_id"] == str(no_loja.id)
    assert payload["account_id"] == str(no_loja.account_id)
    assert payload["protocol_version"] == PROTOCOL_VERSION
    await com.disconnect()


async def test_hello_marca_o_no_como_ativo(como_nuvem, no_loja):
    com = await _conectado(no_loja)
    await _ler(com)

    atualizado = await database_sync_to_async(SyncNode.objects.get)(pk=no_loja.pk)
    assert atualizado.status == NodeStatus.ACTIVE
    assert atualizado.last_seen_at is not None
    await com.disconnect()


async def test_a_reconexao_avisa_da_fila_NA_HORA(como_nuvem, conta, no_loja, no_nuvem):
    """A loja volta e recebe o aviso no mesmo handshake.

    Este é o fecho do desvio para a nuvem: o terminal grava lá enquanto a loja
    está fora, e essa venda precisa descer assim que a loja der sinal de vida.
    O agendador avisa de dez em dez segundos — e a reconexão é exatamente o
    instante em que a loja MAIS tem fila. Esperar o próximo tique deixa o
    salão cego com alguém de pé no caixa esperando a conta.
    """
    await database_sync_to_async(SyncEvent.objects.create)(
        account=conta,
        source_node=no_nuvem,
        target_node=no_loja,
        direction=Direction.OUTBOUND,
        entity_type="order",
        entity_id=uuid.uuid4(),
        operation="CREATE",
        payload={"fields": {}},
        sequence=1,
    )

    com = await _conectado(no_loja)
    tipo, _ = await _ler(com)
    assert tipo == MessageType.AUTHENTICATED

    tipo, payload = await _ler(com)
    assert tipo == MessageType.SYNC_AVAILABLE
    assert payload["reason"] == "reconnect"
    await com.disconnect()


async def test_sem_fila_a_reconexao_nao_avisa(como_nuvem, no_loja):
    """Aviso sem fila ensinaria a loja a pedir à toa a cada reconexão."""
    com = await _conectado(no_loja)
    tipo, _ = await _ler(com)
    assert tipo == MessageType.AUTHENTICATED

    # `receive_nothing` em vez de esperar exceção: `CancelledError` herda de
    # `BaseException`, e `pytest.raises(Exception)` não a pegaria — o teste
    # passaria por engano.
    assert await com.receive_nothing(timeout=1)
    await com.disconnect()


async def test_token_invalido_derruba_a_conexao(como_nuvem, no_loja):
    com = _comunicador(token="token-errado")
    conectado, _ = await com.connect()
    assert conectado
    await com.send_to(text_data=json.dumps(_hello(no_loja), default=str))

    assert await _esperar_fechamento(com) == CloseCode.UNAUTHENTICATED


async def test_mensagem_antes_do_hello_derruba(como_nuvem, no_loja):
    com = _comunicador()
    await com.connect()
    envelope = protocol.build(
        MessageType.HEARTBEAT, source_node_id=no_loja.id, target_node_id=None,
        account_id=no_loja.account_id, payload={},
    )
    await com.send_to(text_data=json.dumps(envelope, default=str))

    assert await _esperar_fechamento(com) == CloseCode.UNAUTHENTICATED


async def test_heartbeat_responde(como_nuvem, no_loja):
    com = await _conectado(no_loja)
    await _ler(com)

    envelope = protocol.build(
        MessageType.HEARTBEAT, source_node_id=no_loja.id, target_node_id=None,
        account_id=no_loja.account_id, payload={},
    )
    await com.send_to(text_data=json.dumps(envelope, default=str))
    tipo, payload = await _ler(com)

    assert tipo == MessageType.HEARTBEAT
    assert "server_time" in payload
    await com.disconnect()


async def test_json_invalido_nao_derruba_a_conexao(como_nuvem, no_loja):
    """Um cliente com bug não pode tirar a loja do ar."""
    com = await _conectado(no_loja)
    await com.receive_from(timeout=5)

    await com.send_to(text_data="{isto nao e json")
    tipo, payload = await _ler(com)
    assert tipo == MessageType.ERROR
    assert payload["code"] == "bad_json"

    # E a conexão continua viva.
    envelope = protocol.build(
        MessageType.HEARTBEAT, source_node_id=no_loja.id, target_node_id=None,
        account_id=no_loja.account_id, payload={},
    )
    await com.send_to(text_data=json.dumps(envelope, default=str))
    tipo, _ = await _ler(com)
    assert tipo == MessageType.HEARTBEAT
    await com.disconnect()


async def test_lote_e_persistido_e_confirmado(como_nuvem, conta, no_loja, no_nuvem):
    com = await _conectado(no_loja)
    await _ler(com)

    payload_evento = {
        "schema_version": 1, "entity_type": "customer", "entity_id": str(uuid.uuid4()),
        "entity_version": 5, "origin_node_id": str(no_loja.id),
        "fields": {"account_id": str(conta.id), "name": "Cliente WS"},
    }
    evento = {
        "event_id": str(uuid.uuid4()), "account_id": str(conta.id),
        "target_node_id": str(no_nuvem.id), "sequence": 1, "entity_type": "customer",
        "entity_id": payload_evento["entity_id"], "operation": "UPSERT",
        "entity_version": 5, "payload": payload_evento,
        "payload_checksum": crypto.checksum(payload_evento),
    }
    envelope = protocol.build(
        MessageType.EVENT_BATCH, source_node_id=no_loja.id, target_node_id=no_nuvem.id,
        account_id=conta.id, payload={"events": [evento]},
    )
    await com.send_to(text_data=json.dumps(envelope, default=str))
    tipo, payload = await _ler(com)

    assert tipo == MessageType.ACK
    assert payload["stored"] == 1

    gravados = await database_sync_to_async(
        SyncEvent.objects.filter(direction=Direction.INBOUND).count
    )()
    assert gravados == 1  # persistido ANTES do ACK
    await com.disconnect()


async def test_lote_de_outra_conta_e_recusado_e_derruba(
    como_nuvem, conta, outra_conta, no_loja, no_nuvem
):
    """A trava central: o payload não autoriza nada."""
    com = await _conectado(no_loja)
    await _ler(com)

    evento = {
        "event_id": str(uuid.uuid4()),
        "account_id": str(outra_conta.id),  # adulterado
        "target_node_id": str(no_nuvem.id), "sequence": 1,
        "entity_type": "customer", "entity_id": str(uuid.uuid4()),
        "operation": "UPSERT", "payload": {"fields": {}},
    }
    envelope = protocol.build(
        MessageType.EVENT_BATCH, source_node_id=no_loja.id, target_node_id=no_nuvem.id,
        account_id=conta.id, payload={"events": [evento]},
    )
    await com.send_to(text_data=json.dumps(envelope, default=str))

    assert await _esperar_fechamento(com) == CloseCode.FORBIDDEN


async def test_sincronizacao_desligada_recusa_a_conexao(settings, como_nuvem, no_loja):
    settings.SYNC_ENABLED = False
    com = _comunicador()
    conectado, codigo = await com.connect()
    assert conectado is False
    assert codigo == CloseCode.WRONG_ENVIRONMENT


async def test_pull_sem_nada_pendente_responde_zero(como_nuvem, no_loja, no_nuvem):
    await database_sync_to_async(
        SyncEvent.objects.filter(direction=Direction.OUTBOUND).delete
    )()
    com = await _conectado(no_loja)
    await _ler(com)

    envelope = protocol.build(
        MessageType.SYNC_PULL_REQUEST, source_node_id=no_loja.id,
        target_node_id=no_nuvem.id, account_id=no_loja.account_id, payload={},
    )
    await com.send_to(text_data=json.dumps(envelope, default=str))
    tipo, payload = await _ler(com)

    assert tipo == MessageType.SYNC_AVAILABLE
    assert payload["pending"] == 0
    await com.disconnect()


async def test_hello_CIFRADO_e_aceito(como_nuvem, no_loja):
    """O handshake real: a loja já tem a chave, então o HELLO vem cifrado.

    Este é o teste que faltava. Os outros mandam o HELLO em claro, e por isso
    atravessavam um ovo-e-galinha: o consumer só definia `self.key` DENTRO do
    `handle_hello`, mas o `receive` decifra ANTES de despachar. Com o HELLO
    cifrado — que é o que acontece em produção — a nuvem recusava a própria
    mensagem de abertura com "mensagem cifrada recebida sem chave configurada",
    e nenhuma loja passava do handshake.
    """
    com = _comunicador()
    conectado, _ = await com.connect()
    assert conectado

    cifrado = protocol.build(
        MessageType.HELLO, source_node_id=no_loja.id, target_node_id=None,
        account_id=no_loja.account_id, payload=_hello(no_loja)["payload"]
        if "payload" in _hello(no_loja) else protocol.parse(_hello(no_loja)),
        key=CHAVE_DE_TESTE,
    )
    assert "ciphertext" in cifrado, "o HELLO deste teste precisa ir CIFRADO"

    await com.send_to(text_data=json.dumps(cifrado, default=str))
    tipo, payload = await _ler(com)

    assert tipo == MessageType.AUTHENTICATED
    assert payload["node_id"] == str(no_loja.id)
    await com.disconnect()
