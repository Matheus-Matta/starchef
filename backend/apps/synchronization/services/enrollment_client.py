"""Lado LOJA da matrícula: pede o pacote, instala e dispara a carga inicial.

Roda uma vez por instalação — ou de novo, sempre que a loja precisar de
credencial nova. É idempotente: rematricular reaproveita o mesmo nó na nuvem
(mesmo `pair_id`), então nada é duplicado lá.
"""
import logging

import requests
from django.conf import settings
from django.db import transaction

from apps.synchronization.constants import NodeType
from apps.synchronization.models import SyncNode
from apps.synchronization.services import enrollment, guard, nodes
from apps.synchronization.services.enrollment_identity import (
    _garantir_conta,
    _gravar_no,
)

logger = logging.getLogger(__name__)

TIMEOUT = 60
CAMINHO = "/api/v1/sync/enroll/"


class EnrollmentError(RuntimeError):
    """A nuvem recusou a matrícula ou não respondeu."""


def already_enrolled():
    """Já existe identidade local utilizável?"""
    if not getattr(settings, "SYNC_AUTH_TOKEN", ""):
        return False
    return SyncNode.objects.filter(is_self=True, node_type=NodeType.LOCAL).exists()


def request_package(*, api_url, username, password, account_id, secret, node_name,
                    restaurant_id=None, cloud_wss_url="", existing_node_id=None):
    """Chama a nuvem e devolve o pacote já decifrado."""
    guard.ensure_environment()
    url = api_url.rstrip("/") + CAMINHO
    corpo = {
        "username": username,
        "password": password,
        "account_id": str(account_id),
        "enrollment_secret": secret,
        "node_name": node_name,
        "restaurant_id": str(restaurant_id) if restaurant_id else None,
        "cloud_wss_url": cloud_wss_url,
        "existing_node_id": str(existing_node_id) if existing_node_id else None,
    }

    try:
        resposta = requests.post(url, json=corpo, timeout=TIMEOUT)
    except requests.RequestException as erro:
        # Sem internet na primeira instalação: a loja ainda não tem dado
        # nenhum, mas também não pode travar o boot por causa disso.
        raise EnrollmentError(f"Não foi possível falar com a nuvem ({url}): {erro}") from erro

    if resposta.status_code >= 400:
        detalhe = _detalhe(resposta)
        raise EnrollmentError(f"A nuvem recusou a matrícula ({resposta.status_code}): {detalhe}")

    dados = resposta.json()
    envelope = dados.get("package") or dados.get("data", {}).get("package")
    if not envelope:
        raise EnrollmentError("Resposta da nuvem sem o pacote de credenciais.")
    return enrollment.decifrar(envelope, secret)


def _detalhe(resposta):
    try:
        corpo = resposta.json()
    except ValueError:
        return resposta.text[:300]
    erro = corpo.get("error") or {}
    return erro.get("message") or corpo.get("detail") or str(corpo)[:300]


def install(pacote, *, env_path=None):
    """Grava a identidade local e, opcionalmente, persiste o `.env`.

    Sem gravar o arquivo, o token vale só para este processo: o container
    reinicia e a loja perde a credencial. Por isso `env_path` é o caminho
    normal em produção — no compose ele aponta para um volume.
    """
    conta_id = pacote.get("SYNC_ACCOUNT_ID")
    node_id = pacote.get("SYNC_NODE_ID")
    pair_id = pacote.get("SYNC_PAIR_ID")
    if not (conta_id and node_id and pair_id):
        raise EnrollmentError("Pacote de matrícula incompleto.")

    with transaction.atomic():
        _garantir_conta(conta_id)
        proprio = _gravar_no(node_id, pair_id, conta_id, NodeType.LOCAL,
                             pacote.get("SYNC_NODE_NAME", "Servidor da loja"), is_self=True)
        peer_id = pacote.get("SYNC_PEER_NODE_ID")
        if peer_id:
            par = _gravar_no(peer_id, pair_id, conta_id, NodeType.CLOUD, "Nuvem", is_self=False)
            proprio.peer = par
            proprio.save(update_fields=["peer", "updated_at"])

    _aplicar_em_runtime(pacote)
    nodes.invalidate_cache()
    if env_path:
        _gravar_env(pacote, env_path)
    return proprio


def _aplicar_em_runtime(pacote):
    """Deixa o processo atual já usável, sem esperar um restart."""
    for chave in ("SYNC_NODE_ID", "SYNC_PAIR_ID", "SYNC_ACCOUNT_ID", "SYNC_STORE_ID",
                  "SYNC_PEER_NODE_ID", "SYNC_CLOUD_WSS_URL", "SYNC_AUTH_TOKEN",
                  "SYNC_ENCRYPTION_KEY", "SYNC_ENCRYPTION_KEY_ID"):
        if pacote.get(chave):
            setattr(settings, chave, pacote[chave])


def _gravar_env(pacote, env_path):
    linhas = [f"{chave}={valor}" for chave, valor in pacote.items() if valor not in (None, "")]
    with open(env_path, "w", encoding="utf-8") as arquivo:
        arquivo.write("# Gerado por sync_enroll. Contém segredo: não versionar.\n")
        arquivo.write("\n".join(linhas) + "\n")
    logger.info("sync-enroll: credenciais gravadas em %s", env_path)
