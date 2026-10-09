"""Quem vence quando os dois lados mexeram no mesmo registro: o MAIS NOVO.

A loja é um clone da nuvem e as duas escrevem — o terminal alterna entre elas
quando a loja oscila. A regra é uma só, para toda entidade e nos dois
sentidos: a versão é o `updated_at` de ORIGEM em microssegundos; a mais nova
entra, a mais antiga não muda nada.

Ela substituiu a política por dono ("a loja vence", "a nuvem vence"), que
recusava a versão mais nova do outro lado e abria conflito. Com o terminal
alternando, o mesmo pedido era editado nos dois servidores com segundos de
diferença: cada edição virava um conflito, a loja ficava com o total antigo e
alguém precisava resolver à mão o que a ordem dos horários já respondia.

Só `MANUAL` continua indo para revisão de gente — hoje nenhuma entrada usa.
A política do catálogo segue valendo para a ADOÇÃO (`adoption.py`): quem
cede a linha quando os dois criaram o mesmo registro com ids diferentes.
"""
import logging

from apps.synchronization.constants import (
    ENTIDADES_FISCAIS, ConflictResolution, ConflictStatus, Direction, EventStatus)
from apps.synchronization.services.registry import registry

logger = logging.getLogger(__name__)

#: O que `decide` devolve.
APLICAR = "apply"
IGNORAR = "ignore"
CONFLITO = "conflict"


def decide(entity_type, *, local_version, remote_version, receiving_node_type, local_exists,
           local_instance=None):
    """`APLICAR`, `IGNORAR` ou `CONFLITO` para uma versão que acabou de chegar.

    Registro que ainda não existe aqui é sempre aplicado: não há o que
    conflitar. Versão igual é a mesma já aplicada (reenvio depois de timeout),
    e a origem recebe ACK do mesmo jeito.
    """
    if not local_exists:
        return APLICAR
    if remote_version == local_version:
        # Sem fonte de versão, "igual" é a constante 1 comparada com ela mesma
        # — não quer dizer "já apliquei". Quem decide é a comparação de
        # CONTEÚDO em `apply._atualizar`, que não grava campos iguais.
        from apps.synchronization.services import serialization

        if serialization.tem_fonte_de_versao(local_instance):
            return IGNORAR
    if _politica(entity_type) == ConflictResolution.MANUAL:
        return CONFLITO
    if remote_version > local_version:
        return APLICAR
    if _linha_local_nunca_sincronizou(entity_type, local_instance):
        return APLICAR
    if remote_version < local_version:
        return IGNORAR
    return APLICAR


def _linha_local_nunca_sincronizou(entity_type, local_instance):
    """A linha daqui é um esqueleto, sem edição nenhuma a proteger?

    A matrícula cria um esqueleto de `Account` para segurar as chaves
    estrangeiras, e ele nasce com `updated_at` de AGORA — sempre "mais novo"
    que o registro real da nuvem, que pode não ser editado há meses. Sem esta
    exceção a loja descartava o dado verdadeiro e a conta seguia chamando
    "(aguardando sincronização)", inativa.

    Esqueleto é a linha que nunca entrou na sincronização: nenhum evento de
    saída (toda edição daqui vira um) e nenhum de entrada aplicado. Uma linha
    com qualquer um dos dois tem história, e aí a versão decide.

    O fiscal fica de fora: para ele a versão decide sempre.
    """
    from django.db.models import Q

    from apps.synchronization.models import SyncEvent

    if local_instance is None or entity_type in ENTIDADES_FISCAIS:
        return False
    # O evento que está sendo aplicado agora também é desta linha: só conta a
    # entrada que JÁ foi aplicada.
    return not SyncEvent.objects.filter(
        Q(direction=Direction.OUTBOUND)
        | Q(direction=Direction.INBOUND,
            status__in=[EventStatus.APPLIED, EventStatus.ACKNOWLEDGED]),
        entity_type=entity_type, entity_id=str(local_instance.pk),
    ).exists()


def _politica(entity_type):
    entrada = registry.get(entity_type)
    return entrada.conflict_policy if entrada else ConflictResolution.MANUAL


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
