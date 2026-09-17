"""O laço assíncrono do worker, com uma conexão falsa no lugar do WebSocket.

O que se mede aqui é a decisão, não a rede: o que o worker faz ao receber cada
tipo de mensagem, e se ele desiste quando deveria insistir. Uma conexão de
mentira deixa isso determinístico — com socket de verdade, o teste mediria a
sorte do agendador.
"""
import asyncio

import pytest

from apps.synchronization.constants import MessageType
from apps.synchronization.worker import LocalSyncWorker

pytestmark = pytest.mark.asyncio


class ConexaoFalsa:
    """Uma conexão que devolve o roteiro combinado e anota o que foi enviado."""

    def __init__(self, roteiro=None, peer_node_id="peer-1"):
        self.roteiro = list(roteiro or [])
        self.peer_node_id = peer_node_id
        self.enviados = []
        self.fechada = False
        self.authenticated = asyncio.Event()
        self.node_id = "no-1"

    async def connect(self):
        return self

    async def send(self, message_type, payload, **kwargs):
        self.enviados.append((message_type, payload, kwargs))
        return {"message_type": message_type}

    async def receive(self, timeout=None):
        if not self.roteiro:
            await asyncio.sleep(0.01)
            return None
        return self.roteiro.pop(0)

    async def close(self):
        self.fechada = True


def _worker(**kwargs):
    config = {
        "url": "wss://n.test/ws/sync/v1/", "token": "t", "node_id": "no-1",
        "pair_id": "p-1", "account_id": "c-1", "key": None, "key_id": "",
        "app_version": "3.0.0",
    }
    return LocalSyncWorker(config=config, once=True, **kwargs)


async def test_handshake_recusado_levanta(monkeypatch):
    """A nuvem respondendo ERROR no HELLO não pode virar laço de reconexão mudo."""
    conexao = ConexaoFalsa(roteiro=[
        (MessageType.ERROR, {}, {"reason": "Credencial inválida."}),
    ])
    worker = _worker()
    with pytest.raises(PermissionError, match="Credencial inválida"):
        await worker._esperar_autenticacao(conexao, timeout=1)


async def test_handshake_sem_resposta_estoura_o_tempo():
    conexao = ConexaoFalsa(roteiro=[])
    worker = _worker()
    with pytest.raises(TimeoutError, match="não respondeu ao HELLO"):
        await worker._esperar_autenticacao(conexao, timeout=0.2)


async def test_sync_available_dispara_um_pull():
    """A nuvem avisa que tem novidade; o worker pede o lote."""
    conexao = ConexaoFalsa()
    worker = _worker()
    await worker._tratar(conexao, MessageType.SYNC_AVAILABLE, {"message_id": "m"}, {})

    tipos = [t for t, _p, _k in conexao.enviados]
    assert MessageType.SYNC_PULL_REQUEST in tipos


async def test_error_da_nuvem_nao_envia_nada():
    conexao = ConexaoFalsa()
    worker = _worker()
    await worker._tratar(
        conexao, MessageType.ERROR, {"message_id": "m"}, {"reason": "versão incompatível"}
    )
    assert conexao.enviados == []


async def test_tipo_desconhecido_e_ignorado_sem_quebrar():
    """Mensagem que esta versão não conhece não derruba a conexão (§17)."""
    conexao = ConexaoFalsa()
    worker = _worker()
    await worker._tratar(conexao, "MENSAGEM_DO_FUTURO", {"message_id": "m"}, {})
    assert conexao.enviados == []


@pytest.mark.django_db(transaction=True)
async def test_lote_recebido_e_confirmado_e_aplicado(como_loja, conta, no_loja, no_nuvem):
    """O ciclo do worker: grava, confirma o recebimento, aplica, confirma de novo."""
    import uuid

    from asgiref.sync import sync_to_async

    from apps.restaurants.models import Restaurant
    from apps.synchronization.services import crypto

    # Um evento real carrega TODOS os campos obrigatórios; o restaurante do
    # cliente é um deles.
    restaurante = await sync_to_async(Restaurant.objects.create)(
        account=conta, legal_name="Loop LTDA", trade_name="Loop"
    )
    payload_evento = {
        "schema_version": 1, "entity_type": "customer", "entity_id": str(uuid.uuid4()),
        "entity_version": 3, "origin_node_id": str(no_nuvem.id),
        "fields": {
            "account_id": str(conta.id), "restaurant_id": str(restaurante.id),
            "name": "Cliente do laço",
        },
    }
    evento = {
        "event_id": str(uuid.uuid4()), "account_id": str(conta.id),
        "target_node_id": str(no_loja.id), "sequence": 1, "entity_type": "customer",
        "entity_id": payload_evento["entity_id"], "operation": "UPSERT",
        "entity_version": 3, "payload": payload_evento,
        "payload_checksum": crypto.checksum(payload_evento),
    }

    conexao = ConexaoFalsa(peer_node_id=str(no_nuvem.id))
    worker = _worker()
    await worker._tratar(
        conexao, MessageType.EVENT_BATCH, {"message_id": "m"}, {"events": [evento]}
    )

    tipos = [t for t, _p, _k in conexao.enviados]
    assert tipos.count(MessageType.ACK) == 2  # "recebi" e depois "apliquei"

    recebidos = conexao.enviados[0][1]["received"]
    assert recebidos == [evento["event_id"]]
    assert conexao.enviados[1][1]["acknowledged"]

    from apps.customers.models import Customer

    existe = await sync_to_async(
        Customer.all_objects.filter(pk=payload_evento["entity_id"]).exists
    )()
    assert existe


async def test_stop_encerra_o_laco():
    worker = _worker()
    assert worker.parar.is_set() is False
    worker.stop()
    assert worker.parar.is_set() is True


async def test_once_nao_reconecta(monkeypatch):
    """Com `--once` o worker tenta uma vez e sai, em vez de ficar em laço."""
    tentativas = {"n": 0}

    class Recusa(ConexaoFalsa):
        async def connect(self):
            tentativas["n"] += 1
            raise ConnectionRefusedError("nuvem fora do ar")

    monkeypatch.setattr(
        "apps.synchronization.worker.transport.CloudConnection",
        lambda **_kwargs: Recusa(),
    )
    worker = _worker()
    await worker.run()
    assert tentativas["n"] == 1
