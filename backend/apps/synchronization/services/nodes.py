"""Quem sou eu e quem é o outro lado.

Todo caminho da sincronização precisa responder isso antes de qualquer coisa,
e a resposta não pode custar uma consulta por evento — daí o cache curto.
"""
from django.core.cache import cache

from apps.synchronization.constants import NodeStatus, NodeType
from apps.synchronization.models import SyncNode
from apps.synchronization.services import guard

CACHE_SELF = "sync:self-node"
CACHE_TTL = 30  # segundos: revogar um nó tem de doer rápido


class NodeNotConfigured(RuntimeError):
    """Esta instalação não tem um SyncNode próprio configurado."""


def self_node(*, use_cache=True):
    """O SyncNode que representa ESTA instalação.

    Identificado por `is_self=True` e pelo `SYNC_NODE_ID` da env. Sem ele não
    há origem para os eventos, então quem chama recebe uma exceção explícita
    em vez de gravar evento órfão.
    """
    if use_cache:
        em_cache = cache.get(CACHE_SELF)
        if em_cache:
            no = SyncNode.objects.filter(pk=em_cache).first()
            if no is not None:
                return no

    from django.conf import settings

    node_id = getattr(settings, "SYNC_NODE_ID", "")
    consulta = SyncNode.objects.filter(is_self=True)
    if node_id:
        consulta = consulta.filter(pk=node_id)
    no = consulta.first()
    if no is None:
        raise NodeNotConfigured(
            "Nenhum SyncNode com is_self=True nesta instalação. "
            "Rode `manage.py sync_provision_node` (nuvem) ou `sync_install_node` (loja)."
        )
    cache.set(CACHE_SELF, str(no.pk), CACHE_TTL)
    return no


def self_node_or_none():
    """Igual a `self_node`, mas devolve None em vez de levantar.

    É a versão que a captura de outbox usa: uma instalação sem sincronização
    configurada tem de continuar gravando pedidos normalmente.

    O `atomic()` não é decoração. No PostgreSQL, uma consulta que falha aborta
    a transação inteira — e engolir o erro em Python não a desfaz: o próximo
    comando morre com "current transaction is aborted". Dentro do bloco, a
    falha rola de volta só o savepoint, e quem chamou segue com a transação
    dele intacta. É o que mantém a promessa deste módulo: sincronização
    quebrada nunca derruba a gravação do dado de negócio.
    """
    from django.db import transaction

    try:
        with transaction.atomic():
            return self_node()
    except Exception:  # noqa: BLE001 — banco ainda migrando, cache frio, etc.
        return None


def peer_of(no):
    """O nó do outro lado do mesmo `pair_id`."""
    if no.peer_id:
        return no.peer
    return SyncNode.objects.filter(pair_id=no.pair_id).exclude(pk=no.pk).first()


def targets_for(no, account_id):
    """Para quem esta instalação envia o que ela originou.

    - Na LOJA há um destino só: a nuvem daquele vínculo.
    - Na NUVEM há um destino por loja ativa da conta — e é por isso que a
      filtragem por `account` aqui não é opcional: sem ela a conta A receberia
      evento da conta B.
    """
    if no.node_type == NodeType.LOCAL:
        par = peer_of(no)
        return [par] if par is not None and par.is_active else []

    return list(
        SyncNode.objects.filter(
            account_id=account_id,
            node_type=NodeType.LOCAL,
            is_active=True,
            status__in=list(NodeStatus.CONNECTABLE),
        ).exclude(pk=no.pk)
    )


def is_cloud():
    return guard.node_type() == NodeType.CLOUD


def is_local():
    return guard.node_type() == NodeType.LOCAL


def invalidate_cache():
    cache.delete(CACHE_SELF)
