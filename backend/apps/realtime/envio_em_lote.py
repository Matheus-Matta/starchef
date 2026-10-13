"""Os avisos de tempo real de uma requisição, enviados JUNTOS no fim dela.

Cada registro salvo gera um aviso (`realtime/signals.py`), e cada aviso era um
`async_to_sync(group_send)` próprio: laço de eventos novo, e com ele conexão
nova ao Redis, DNS de novo. Uma venda de 50 itens soltava 261 — 2 s dos 5,6 s
da conclusão, com o caixa esperando (medido com cProfile no alvo de carga).

Dentro de uma requisição (`RealtimeEmLoteMiddleware`) os avisos entram num
lote e saem no fim, num laço só e numa conexão só. O mesmo registro avisado
várias vezes (o pedido é salvo umas oito numa venda) vira um aviso, o último:
quem escuta relê o registro, e o estado final é o que importa. Fora de uma
requisição (Celery, shell) o aviso sai na hora, como antes.

Redis fora nunca derruba a requisição: a venda já foi gravada, e o aviso é só
"releia". Fica no log.
"""
import contextvars
import logging
from contextlib import contextmanager

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

_lote = contextvars.ContextVar("realtime_lote", default=None)


def enviar(grupo, mensagem):
    """Envia agora, ou guarda no lote da requisição em curso."""
    pendentes = _lote.get()
    if pendentes is None:
        _enviar_agora([(grupo, mensagem)])
    else:
        pendentes.append((grupo, mensagem))


@contextmanager
def em_lote():
    """Junta os avisos de dentro do bloco e os envia de uma vez no fim."""
    token = _lote.set([])
    try:
        yield
    finally:
        pendentes = _lote.get()
        _lote.reset(token)
        if pendentes:
            _enviar_agora(_sem_repetidos(pendentes))


def _chave(grupo, mensagem):
    """O que identifica "o mesmo aviso": o mesmo evento do mesmo registro."""
    payload = mensagem.get("payload") or {}
    if isinstance(payload, dict) and payload.get("id") and payload.get("resource"):
        return (grupo, mensagem.get("type"), mensagem.get("event"),
                payload["resource"], payload["id"])
    # Sem identidade de registro (cozinha, invalidação de coleção): só a
    # repetição exata se junta.
    return (grupo, repr(mensagem))


def _sem_repetidos(pendentes):
    """Um aviso por chave, o ÚLTIMO, na ordem em que cada um ficou final."""
    ultimo = {}
    for grupo, mensagem in pendentes:
        chave = _chave(grupo, mensagem)
        ultimo.pop(chave, None)
        ultimo[chave] = (grupo, mensagem)
    return list(ultimo.values())


def _enviar_agora(mensagens):
    camada = get_channel_layer()
    if not camada or not mensagens:
        return

    async def _todas():
        for grupo, mensagem in mensagens:
            await camada.group_send(grupo, mensagem)

    try:
        async_to_sync(_todas)()
    except Exception:  # noqa: BLE001 — aviso perdido não desfaz o que foi gravado
        logger.warning("Avisos de tempo real não enviados (%d).", len(mensagens), exc_info=True)


class RealtimeEmLoteMiddleware:
    """Envolve a requisição num lote de avisos (ver o topo do módulo)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with em_lote():
            return self.get_response(request)
