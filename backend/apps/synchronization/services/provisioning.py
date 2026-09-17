"""Cadastro do vínculo e geração das credenciais (§7).

O token e a chave saem daqui UMA vez, no pacote de configuração. Depois disso
o banco só tem o hash do token e a impressão digital da chave — não há como
recuperá-los, e é assim que tem de ser.
"""
import uuid

from django.db import transaction
from django.utils import timezone

from apps.synchronization.constants import ENVIRONMENT_DEVELOPMENT, NodeStatus, NodeType
from apps.synchronization.models import SyncNode
from apps.synchronization.services import crypto, guard, nodes


def provision_local_node(*, account, restaurant=None, name, endpoint="", allowed_ip=None,
                         cloud_endpoint="", pair_id=None):
    """Cadastra o nó da loja na nuvem e devolve `(no, pacote)`.

    O `pacote` é o que vai para o `.env.local` da loja. Ele contém o segredo —
    mostre uma vez e não guarde.
    """
    guard.ensure_environment()

    par = pair_id or uuid.uuid4()
    token = crypto.generate_token()
    chave = crypto.generate_key()
    key_id = f"dev-{uuid.uuid4().hex[:8]}"

    with transaction.atomic():
        no = SyncNode.objects.create(
            pair_id=par,
            account=account,
            restaurant=restaurant,
            node_type=NodeType.LOCAL,
            environment=ENVIRONMENT_DEVELOPMENT,
            name=name,
            endpoint=endpoint,
            allowed_ip=allowed_ip,
            credential_hash=crypto.hash_token(token),
            credential_rotated_at=timezone.now(),
            encryption_key_id=key_id,
            secret_fingerprint=crypto.fingerprint(chave),
            status=NodeStatus.PENDING,
        )
        proprio = ensure_self_node(account=account, node_type=NodeType.CLOUD, pair_id=par)
        no.peer = proprio
        no.save(update_fields=["peer", "updated_at"])

    pacote = {
        "SYNC_ENABLED": "true",
        "SYNC_ENVIRONMENT": ENVIRONMENT_DEVELOPMENT,
        "SYNC_NODE_TYPE": "local",
        "SYNC_NODE_ID": str(no.id),
        "SYNC_PAIR_ID": str(no.pair_id),
        "SYNC_ACCOUNT_ID": str(account.id),
        "SYNC_STORE_ID": str(restaurant.id) if restaurant else "",
        "SYNC_CLOUD_WSS_URL": cloud_endpoint or endpoint,
        "SYNC_AUTH_TOKEN": token,
        "SYNC_ENCRYPTION_KEY": chave,
        "SYNC_ENCRYPTION_KEY_ID": key_id,
        "SYNC_PEER_NODE_ID": str(proprio.id),
    }
    return no, pacote


def ensure_self_node(*, account, node_type, pair_id, name=None, node_id=None):
    """O registro que representa ESTA instalação. Idempotente de propósito."""
    guard.ensure_environment()

    existente = SyncNode.objects.filter(
        account=account, node_type=node_type, pair_id=pair_id, is_self=True
    ).first()
    if existente is not None:
        return existente

    return SyncNode.objects.create(
        id=node_id or uuid.uuid4(),
        pair_id=pair_id,
        account=account,
        node_type=node_type,
        environment=ENVIRONMENT_DEVELOPMENT,
        name=name or f"{node_type} {account}",
        status=NodeStatus.ACTIVE,
        is_self=True,
    )


def rotate_credentials(no):
    """Gera token e chave novos. O anterior para de valer na hora."""
    guard.ensure_environment()

    token = crypto.generate_token()
    chave = crypto.generate_key()
    no.credential_hash = crypto.hash_token(token)
    no.secret_fingerprint = crypto.fingerprint(chave)
    no.encryption_key_id = f"dev-{uuid.uuid4().hex[:8]}"
    no.credential_rotated_at = timezone.now()
    no.save(update_fields=[
        "credential_hash", "secret_fingerprint", "encryption_key_id",
        "credential_rotated_at", "updated_at",
    ])
    return {
        "SYNC_AUTH_TOKEN": token,
        "SYNC_ENCRYPTION_KEY": chave,
        "SYNC_ENCRYPTION_KEY_ID": no.encryption_key_id,
    }


def revoke(no, *, motivo=""):
    """Revoga o vínculo: a credencial morre e a conexão aberta é encerrada.

    Os eventos pendentes NÃO são apagados. Um nó revogado por engano e
    reativado volta a enviar tudo que ficou para trás.
    """
    no.status = NodeStatus.REVOKED
    no.is_active = False
    no.credential_hash = ""
    no.last_error = motivo or "Revogado manualmente."
    no.save(update_fields=[
        "status", "is_active", "credential_hash", "last_error", "updated_at",
    ])
    nodes.invalidate_cache()
    _derrubar_conexao(no)
    return no


def _derrubar_conexao(no):
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    camada = get_channel_layer()
    if camada is None:  # pragma: no cover — sem Channels configurado
        return
    async_to_sync(camada.group_send)(no.group_name, {"type": "sync.revoked"})


def env_file_text(pacote):
    """O pacote como linhas de `.env`, prontas para copiar."""
    return "\n".join(f"{chave}={valor}" for chave, valor in pacote.items())
