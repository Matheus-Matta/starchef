"""Autenticação do nó no handshake. O que a conexão prova, e só isso.

Depois daqui, `account_id`, `node_id` e `pair_id` vêm do SyncNode encontrado —
nunca do payload. É a diferença entre autenticar e acreditar.
"""
import logging

from django.utils import timezone

from apps.synchronization.constants import NodeStatus, PROTOCOL_VERSION
from apps.synchronization.models import SyncNode
from apps.synchronization.services import crypto, guard

logger = logging.getLogger(__name__)


class AuthenticationFailed(PermissionError):
    """Token inválido, nó revogado, ambiente errado ou versão incompatível."""


def authenticate(hello_payload, *, raw_token, client_ip=None):
    """Valida o HELLO e devolve o SyncNode autenticado.

    A ordem das checagens é a do §9.1, e cada uma delas falha com a MESMA
    mensagem genérica para quem está do outro lado: dizer "token certo, nó
    revogado" entrega informação a quem está tentando adivinhar.
    """
    guard.ensure_enabled()

    node_id = str(hello_payload.get("node_id") or "")
    if not node_id or not raw_token:
        raise AuthenticationFailed("Credencial ausente.")

    no = SyncNode.objects.filter(pk=node_id).select_related("account").first()
    if no is None:
        logger.warning("sync: HELLO com node_id desconhecido ip=%s", client_ip)
        raise AuthenticationFailed("Credencial inválida.")

    if not crypto.token_matches(raw_token, no.credential_hash):
        logger.warning("sync: token inválido node=%s ip=%s", no.id, client_ip)
        raise AuthenticationFailed("Credencial inválida.")

    _validar_estado(no, client_ip)
    _validar_ambiente(no, hello_payload)
    _validar_pair(no, hello_payload)
    _registrar_presenca(no, hello_payload)
    return no


def _validar_estado(no, client_ip):
    if not no.can_connect:
        logger.warning("sync: nó %s recusado (status=%s)", no.id, no.status)
        raise AuthenticationFailed("Credencial inválida.")
    if no.allowed_ip and client_ip and no.allowed_ip != client_ip:
        # IP nunca é a autenticação principal; é uma tranca a mais.
        logger.warning("sync: nó %s de IP inesperado %s", no.id, client_ip)
        raise AuthenticationFailed("Credencial inválida.")


def _validar_ambiente(no, payload):
    ambiente = str(payload.get("environment") or "").strip().lower()
    if not guard.environment_is_allowed(ambiente) or no.environment != ambiente:
        raise AuthenticationFailed(guard.MENSAGEM)

    versao = int(payload.get("protocol_version") or 0)
    if versao != PROTOCOL_VERSION:
        raise AuthenticationFailed(
            f"Versão de protocolo incompatível: {versao} (esperado {PROTOCOL_VERSION})."
        )


def _validar_pair(no, payload):
    pair_id = str(payload.get("pair_id") or "")
    if pair_id and pair_id != str(no.pair_id):
        raise AuthenticationFailed("Credencial inválida.")

    conta = str(payload.get("account_id") or "")
    if conta and conta != str(no.account_id):
        # O payload não autoriza nada, mas divergir aqui denuncia configuração
        # trocada — vale recusar em vez de sincronizar a conta errada.
        logger.error("sync: HELLO com conta divergente node=%s conta=%s", no.id, conta)
        raise AuthenticationFailed("Credencial inválida.")


def _registrar_presenca(no, payload):
    no.status = NodeStatus.ACTIVE
    no.last_seen_at = timezone.now()
    no.app_version = str(payload.get("app_version") or "")[:32]
    no.schema_version = int(payload.get("schema_version") or 0)
    no.protocol_version = int(payload.get("protocol_version") or 0)
    no.last_error = ""
    no.save(update_fields=[
        "status", "last_seen_at", "app_version", "schema_version",
        "protocol_version", "last_error", "updated_at",
    ])


def mark_offline(no, motivo=""):
    """Conexão caiu. OFFLINE, não REVOKED: o nó volta quando a internet voltar."""
    if no.status == NodeStatus.ACTIVE:
        no.status = NodeStatus.OFFLINE
    no.last_error = str(motivo)[:2000]
    no.save(update_fields=["status", "last_error", "updated_at"])
