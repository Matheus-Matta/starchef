"""Lado LOJA: pega o segredo de emissão emprestado, e só em memória.

A regra que dá sentido a todo o canal: **nada aqui toca o disco.** Nem banco,
nem arquivo, nem log. Se persistisse, teríamos trocado o problema de lugar em
vez de resolvê-lo — o segredo voltaria a ficar num computador dentro da loja,
para sempre, e revogar o token do nó não o apagaria de lá.

O cache é de processo e tem prazo. Um backend reiniciado pede de novo, o que é
barato e é exatamente a propriedade desejada: o acesso vive enquanto o vínculo
com a nuvem vive.
"""
import logging
import threading
import time

from django.conf import settings

from apps.synchronization.services import credentials, nodes

logger = logging.getLogger(__name__)

#: Quanto tempo o pacote vale em memória. Curto o bastante para uma revogação
#: surtir efeito rápido, longo o bastante para não pedir a cada venda.
VALIDADE_PADRAO_SEGUNDOS = 300

_TRAVA = threading.Lock()
_CACHE = {"pacote": None, "expira_em": 0.0}


def _validade():
    return int(getattr(settings, "SYNC_CREDENTIALS_TTL_SECONDS", VALIDADE_PADRAO_SEGUNDOS))


def esquecer():
    """Descarta o que está em memória. Use ao revogar ou ao trocar de nó."""
    with _TRAVA:
        _CACHE["pacote"] = None
        _CACHE["expira_em"] = 0.0


def obter(*, forcar=False, client=None):
    """O pacote de credenciais desta loja, de memória ou da nuvem.

    Devolve `None` — e não levanta — quando não dá para obter. Quem chama está
    no caminho de uma venda, e uma falha aqui precisa virar "não emiti e digo o
    porquê", nunca uma exceção subindo até o caixa.
    """
    agora = time.monotonic()
    if not forcar:
        with _TRAVA:
            if _CACHE["pacote"] is not None and _CACHE["expira_em"] > agora:
                return _CACHE["pacote"]

    try:
        pacote = _buscar(client=client)
    except Exception as erro:  # noqa: BLE001 — nunca derrubar a venda
        logger.warning("sync-credenciais: não foi possível obter — %s", erro)
        return None

    with _TRAVA:
        _CACHE["pacote"] = pacote
        _CACHE["expira_em"] = time.monotonic() + _validade()
    return pacote


def _buscar(*, client=None):
    import requests

    proprio = nodes.self_node()
    base = (getattr(settings, "SYNC_CLOUD_API_URL", "") or "").rstrip("/")
    if not base:
        raise credentials.CredentialsUnavailable(
            "SYNC_CLOUD_API_URL não configurada nesta loja."
        )
    token = getattr(settings, "SYNC_AUTH_TOKEN", "") or ""
    if not token:
        raise credentials.CredentialsUnavailable(
            "SYNC_AUTH_TOKEN não configurado: o nó não tem como se identificar."
        )

    http = client or requests
    resposta = http.post(
        f"{base}/api/v1/sync/credentials/",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sync-Node-Id": str(proprio.id),
        },
        timeout=int(getattr(settings, "SYNC_CREDENTIALS_TIMEOUT", 15)),
    )
    if resposta.status_code != 200:
        raise credentials.CredentialsUnavailable(
            f"A nuvem respondeu HTTP {resposta.status_code} ao pedido de credencial."
        )

    corpo = resposta.json()
    # Abre com o id do NÓ como dado associado: um envelope destinado a outra
    # loja não abre aqui, mesmo com a chave do ambiente correta.
    return credentials.abrir(corpo["envelope"], proprio.id)
