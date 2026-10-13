"""Os avisos de tempo real de uma requisição saem JUNTOS, numa conexão só.

Medido numa venda de 50 itens: 261 avisos (um por registro salvo), cada um
num `async_to_sync` próprio — laço de eventos novo, conexão nova ao Redis,
DNS de novo. 2 s dos 5,6 s da venda, com o caixa esperando.
"""
from apps.realtime import envio_em_lote
from apps.realtime.events import broadcast_model_event


class CamadaFalsa:
    def __init__(self):
        self.enviados = []

    async def group_send(self, grupo, mensagem):
        self.enviados.append((grupo, mensagem))


def _aviso(id_, campos=()):
    return {"resource": "orders.order", "id": id_, "changed_fields": list(campos)}


def test_na_requisicao_os_avisos_saem_num_lote_so_e_sem_repeticao(monkeypatch):
    camada = CamadaFalsa()
    chamadas = []
    monkeypatch.setattr(envio_em_lote, "get_channel_layer", lambda: camada)
    original = envio_em_lote.async_to_sync
    monkeypatch.setattr(envio_em_lote, "async_to_sync",
                        lambda f: chamadas.append(f) or original(f))

    with envio_em_lote.em_lote():
        broadcast_model_event("conta1", "model.updated", _aviso("p1", ["total"]))
        broadcast_model_event("conta1", "model.created", _aviso("i1"))
        broadcast_model_event("conta1", "model.updated", _aviso("p1", ["status"]))
        assert camada.enviados == []  # nada sai antes do fim

    assert len(chamadas) == 1  # um laço, uma conexão
    eventos = [(m["event"], m["payload"]["id"], m["payload"]["changed_fields"])
               for _, m in camada.enviados]
    # O pedido salvo duas vezes vira UM aviso, o último.
    assert eventos == [("model.created", "i1", []), ("model.updated", "p1", ["status"])]


def test_fora_de_requisicao_o_aviso_sai_na_hora(monkeypatch):
    camada = CamadaFalsa()
    monkeypatch.setattr(envio_em_lote, "get_channel_layer", lambda: camada)

    broadcast_model_event("conta1", "model.updated", _aviso("p1"))

    assert len(camada.enviados) == 1


def test_redis_fora_nao_derruba_a_requisicao(monkeypatch):
    class CamadaQuebrada:
        async def group_send(self, *_):
            raise ConnectionError("redis fora")

    monkeypatch.setattr(envio_em_lote, "get_channel_layer", CamadaQuebrada)
    with envio_em_lote.em_lote():
        broadcast_model_event("conta1", "model.updated", _aviso("p1"))
