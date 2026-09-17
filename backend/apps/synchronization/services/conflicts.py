"""Quem vence quando os dois lados mexeram no mesmo registro.

O princípio do §15: sincronização bidirecional NÃO autoriza sobrescrita
irrestrita. Dado financeiro e fiscal nunca é resolvido em silêncio por
last-write-wins — ele vira um SyncConflict e espera decisão humana.
"""
import logging

from apps.synchronization.constants import ConflictResolution, ConflictStatus, NodeType
from apps.synchronization.services.registry import registry

logger = logging.getLogger(__name__)

#: O que `decide` devolve.
APLICAR = "apply"
IGNORAR = "ignore"
CONFLITO = "conflict"


def decide(entity_type, *, local_version, remote_version, receiving_node_type, local_exists):
    """`APLICAR`, `IGNORAR` ou `CONFLITO` para uma versão que acabou de chegar.

    Registro que ainda não existe aqui é sempre aplicado: não há o que
    conflitar. Versão já aplicada é ignorada (a origem recebe ACK do mesmo
    jeito — reenvio depois de timeout não pode duplicar nada).
    """
    if not local_exists:
        return APLICAR
    if remote_version == local_version:
        return IGNORAR
    if remote_version < local_version:
        return _decidir_versao_antiga(entity_type, receiving_node_type)
    return _decidir_versao_nova(entity_type, receiving_node_type)


def _politica(entity_type):
    entrada = registry.get(entity_type)
    return entrada.conflict_policy if entrada else ConflictResolution.MANUAL


def _decidir_versao_nova(entity_type, receiving_node_type):
    """Chegou algo mais novo que o daqui. Normalmente aplica — menos no fiscal."""
    politica = _politica(entity_type)
    if politica == ConflictResolution.MANUAL:
        return CONFLITO
    if politica == ConflictResolution.CLOUD_WINS and receiving_node_type == NodeType.CLOUD:
        # A nuvem manda nesta entidade e alguém alterou na loja: revisão.
        return CONFLITO
    if politica == ConflictResolution.LOCAL_WINS and receiving_node_type == NodeType.LOCAL:
        # A loja manda e a nuvem tentou mexer: a loja não aceita.
        return CONFLITO
    return APLICAR


def _decidir_versao_antiga(entity_type, receiving_node_type):
    """Chegou algo mais velho que o daqui: ignorar é o certo quase sempre."""
    if _politica(entity_type) == ConflictResolution.MANUAL:
        return CONFLITO
    return IGNORAR


def register(event, *, local_instance, remote_payload, local_version, remote_version):
    """Grava o conflito. Não resolve nada — é justamente o ponto."""
    from apps.synchronization.models import SyncConflict
    from apps.synchronization.services import serialization

    entrada = registry.get(event.entity_type)
    local_fields = (
        serialization.serialize(local_instance, entrada)
        if local_instance is not None and entrada is not None
        else {}
    )
    conflito = SyncConflict.objects.create(
        account_id=event.account_id,
        event=event,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        source_node=event.source_node,
        target_node=event.target_node,
        local_version=local_version,
        remote_version=remote_version,
        local_payload=local_fields,
        remote_payload=remote_payload,
        resolution=_politica(event.entity_type),
        status=ConflictStatus.OPEN,
    )
    logger.warning(
        "sync: conflito aberto entity=%s id=%s local_v=%s remote_v=%s",
        event.entity_type, event.entity_id, local_version, remote_version,
    )
    return conflito


def open_count(account_id=None):
    from apps.synchronization.models import SyncConflict

    consulta = SyncConflict.objects.filter(status=ConflictStatus.OPEN)
    if account_id:
        consulta = consulta.filter(account_id=account_id)
    return consulta.count()
