"""A exclusão também obedece à regra do mais novo.

Dois defeitos tinham o mesmo formato — a exclusão fora da comparação de versão:

* um DELETE atrasado apagava a linha mesmo editada DEPOIS dele;
* uma versão atrasada de uma linha apagada aqui não achava nada e INSERIA: a
  linha excluída voltava, com o dado velho.

A versão de um DELETE é o MOMENTO da exclusão (`outbox.record`), e a lápide é
o próprio evento DELETE — o que esta instalação gravou e mandou, ou o que veio
do outro lado e já foi aplicado.
"""
from django.db.models import Q

from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.services import serialization


def edicao_mais_nova_que_a_exclusao(existente, versao_da_exclusao):
    """A linha daqui foi editada DEPOIS da exclusão que chegou?"""
    return existente is not None and serialization.entity_version(existente) > versao_da_exclusao


def apagada_depois(entity_type, entity_id, remote_version):
    """Existe uma exclusão desta linha mais nova que a versão que chegou?"""
    from apps.synchronization.models import SyncEvent

    return SyncEvent.objects.filter(
        Q(direction=Direction.OUTBOUND)
        | Q(direction=Direction.INBOUND,
            status__in=[EventStatus.APPLIED, EventStatus.ACKNOWLEDGED]),
        entity_type=entity_type, entity_id=str(entity_id),
        operation=Operation.DELETE, entity_version__gte=remote_version,
    ).exists()
