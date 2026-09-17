"""Autenticação por TOKEN DE NÓ nas rotas HTTP da sincronização.

O WebSocket autentica o nó no HELLO. As rotas HTTP (transferência de arquivo,
métricas) precisam do mesmo: quem chama é um servidor, não uma pessoa — não há
JWT de usuário, e não pode haver. Um backend de loja não tem "usuário logado".

O token é o mesmo do handshake, apresentado em `Authorization: Bearer`. O banco
guarda só o hash; a comparação é em tempo constante (ver `services/crypto.py`).
"""
import hmac
import logging

from django.conf import settings
from rest_framework import authentication, exceptions

from apps.synchronization.constants import NodeStatus
from apps.synchronization.models import SyncNode
from apps.synchronization.services import crypto, guard

logger = logging.getLogger(__name__)

CABECALHO_NO = "HTTP_X_SYNC_NODE_ID"


class NodeUser:
    """Identidade não-humana. Nunca vira `request.user` de verdade.

    O DRF exige um objeto com `is_authenticated`; este é ele. Ele não tem
    permissão nenhuma no sistema de permissões do Django de propósito: o que
    um nó pode fazer é decidido pelas views da sincronização, não por perfil.
    """

    is_authenticated = True
    is_anonymous = False
    is_staff = False
    is_superuser = False

    def __init__(self, node):
        self.node = node
        self.account_id = node.account_id
        # O DRF identifica quem chama por `user.pk` (é assim que o throttle
        # conta requisições). Sem isto, toda rota autenticada por nó quebra com
        # AttributeError antes de a view rodar — e o erro não diz o motivo.
        self.pk = f"node-{node.id}"
        self.id = self.pk

    def __str__(self):
        return f"node:{self.node.id}"

    def has_perm(self, *_args, **_kwargs):
        return False


class NodeTokenAuthentication(authentication.BaseAuthentication):
    """`Authorization: Bearer <token>` + `X-Sync-Node-Id: <uuid>`.

    O id do nó vai em cabeçalho próprio porque o token sozinho exigiria varrer
    todos os nós comparando hash — O(n) por requisição e um oráculo de tempo
    de graça. Com o id, é uma busca direta e uma comparação constante.
    """

    keyword = "Bearer"

    def authenticate(self, request):
        node_id = request.META.get(CABECALHO_NO, "").strip()
        if not node_id:
            return None  # não é uma chamada de nó; outra classe que tente

        guard.ensure_enabled()
        token = self._token(request)
        if not token:
            raise exceptions.AuthenticationFailed("Credencial de nó ausente.")

        no = SyncNode.objects.filter(pk=node_id).select_related("account").first()
        if no is None or not crypto.token_matches(token, no.credential_hash):
            logger.warning("sync-http: credencial de nó inválida id=%s", node_id)
            raise exceptions.AuthenticationFailed("Credencial inválida.")

        if not no.is_active or no.status not in NodeStatus.CONNECTABLE:
            logger.warning("sync-http: nó %s recusado (status=%s)", no.id, no.status)
            raise exceptions.AuthenticationFailed("Credencial inválida.")

        return (NodeUser(no), no)

    def _token(self, request):
        bruto = request.META.get("HTTP_AUTHORIZATION", "").strip()
        if not bruto.lower().startswith(f"{self.keyword.lower()} "):
            return ""
        return bruto[len(self.keyword) + 1:].strip()

    def authenticate_header(self, _request):
        return self.keyword


def node_of(request):
    """O SyncNode autenticado desta requisição, ou None."""
    auth = getattr(request, "auth", None)
    return auth if isinstance(auth, SyncNode) else None


def metrics_token_ok(request):
    """Confere o token de raspagem das métricas.

    Separado do token de nó: quem raspa métricas é o Prometheus, que não é nó
    de ninguém. Sem `SYNC_METRICS_TOKEN` configurado, a rota fica restrita a
    superusuário — nunca aberta.
    """
    esperado = getattr(settings, "SYNC_METRICS_TOKEN", "")
    if not esperado:
        return False
    bruto = request.META.get("HTTP_AUTHORIZATION", "").strip()
    apresentado = bruto[7:].strip() if bruto.lower().startswith("bearer ") else ""
    return bool(apresentado) and hmac.compare_digest(apresentado, esperado)
