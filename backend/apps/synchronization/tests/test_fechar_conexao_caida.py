"""Fechar uma conexão que já caiu nunca derruba o sync_worker.

Achado no par Docker (v3.0.89): durante uma queda de rede, o `finally` do laço
fechava a conexão e a biblioteca de WebSocket levantava `AttributeError`
(`'NoneType' object has no attribute 'call_soon'`) — o socket já estava sem
o laço de eventos. O erro escapava do laço que foi feito para "cair é
esperado; desistir não", o processo terminava, e a sincronização ficava
parada até alguém religar o contêiner: no teste, milhares de eventos
pendentes e loja e nuvem divergentes.
"""
import asyncio

import pytest

from apps.synchronization import worker as modulo_worker
from apps.synchronization.services.transport import CloudConnection

pytestmark = pytest.mark.asyncio


class SocketQuebrado:
    async def close(self):
        raise AttributeError("'NoneType' object has no attribute 'call_soon'")


def _conexao():
    return CloudConnection(url="wss://n.test/ws/sync/v1/", token="t", node_id="n",
                           pair_id="p", account_id="c")


async def test_fechar_socket_quebrado_nao_levanta():
    conexao = _conexao()
    conexao.socket = SocketQuebrado()
    conexao.authenticated.set()

    await conexao.close()

    assert conexao.socket is None
    assert not conexao.authenticated.is_set()


async def test_o_laco_do_worker_sobrevive_ao_fechamento_quebrado(monkeypatch):
    class ConexaoQueCai:
        def __init__(self, **_):
            self.authenticated = asyncio.Event()
            self.node_id = "n"

        async def connect(self):
            raise ConnectionError("rede caiu")

        async def close(self):
            raise AttributeError("'NoneType' object has no attribute 'call_soon'")

    monkeypatch.setattr(modulo_worker.transport, "CloudConnection", ConexaoQueCai)
    worker = modulo_worker.LocalSyncWorker(
        config={"url": "wss://n.test/ws/sync/v1/", "token": "t", "node_id": "n",
                "pair_id": "p", "account_id": "c", "key": None, "key_id": "",
                "app_version": "3.0.89"},
        once=True,
    )

    await worker.run()  # antes: AttributeError escapava e matava o processo
