"""A outbox transacional: grava o evento na MESMA transação do dado.

É o ponto em que "o dado não se perde" deixa de ser promessa e vira garantia.
Nada aqui usa `transaction.on_commit`: o plano proíbe (§11.1), e o motivo é
concreto — o processo cair entre o commit do pedido e a criação do evento é
uma venda que existe na loja e nunca existirá na nuvem. Se a transação do
pedido aborta, o evento aborta junto; se ela commita, o evento está lá.

A recuperação depois disso é responsabilidade do estado do próprio SyncEvent:
enquanto não for ACKNOWLEDGED, ele continua no banco com o payload inteiro e
o dispatcher volta a pegá-lo — mesmo depois de reinício, queda de rede ou
semanas offline.
"""
import logging

from django.db import IntegrityError, transaction

from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.services import crypto, nodes, serialization
from apps.synchronization.services.registry import registry

logger = logging.getLogger(__name__)

# Reexportados: a supressão de eco mora em `outbox_eco`, mas quem já importava
# `outbox.is_applying` / `outbox.applying_remote_event` continua importando de
# onde sempre importou.
from apps.synchronization.services.outbox_eco import (  # noqa: E402
    applying_remote_event as applying_remote_event,
)
from apps.synchronization.services.outbox_eco import (  # noqa: E402
    is_applying as is_applying,
)

def record(instance, operation=Operation.UPSERT, *, run=None, force=False):
    """Registra o evento de saída de uma instância. Devolve os eventos criados.

    Silenciosa em três casos, todos deliberados: o model não sincroniza, esta
    instalação não tem nó configurado, ou estamos aplicando um evento remoto.
    Nenhum deles pode derrubar a gravação do dado de negócio.
    """
    if is_applying() and not force:
        return []

    entry = registry.for_model(type(instance))
    if entry is None:
        return []

    origem = nodes.self_node_or_none()
    if origem is None:
        return []

    account_id = getattr(instance, "account_id", None) or _account_de(instance)
    if account_id is None:
        logger.warning("sync: %s sem conta; evento descartado", entry.entity_type)
        return []

    if not _direcao_permitida(entry, origem, operation=operation):
        return []

    destinos = nodes.targets_for(origem, account_id)
    if not destinos:
        return []

    payload = serialization.build_payload(instance, entry, origin_node_id=origem.id)
    return [
        _criar_evento(origem, destino, account_id, entry, payload, operation, run)
        for destino in destinos
    ]


def _direcao_permitida(entry, origem, *, operation=Operation.UPSERT):
    """A entidade pode sair DESTA instalação, nesta operação?

    `seed_to_local` vale SÓ no SNAPSHOT, e a distinção é o ponto todo. Pedido e
    sessão de caixa nascem na loja e sobem: a nuvem empurrá-los para baixo no
    dia a dia brigaria com o que a loja está escrevendo naquele instante. Mas
    uma loja que ASSUME a operação começa com o banco vazio e precisa receber o
    estado vivo uma vez — e `SNAPSHOT` é exatamente essa uma vez, usada só pela
    carga (`bootstrap._gerar_entidade`).

    Sem isto, a carga percorria as 12 sessões de caixa, chamava `record` para
    cada uma e recebia lista vazia de volta: a corrida terminava "COMPLETED,
    483 processados, 0 falhas" sem ter gerado um evento sequer. O portão da
    carga (`bootstrap._flui_para`) já conhecia a semeadura; este aqui não.
    """
    if nodes.is_cloud():
        if registry.flows_to_local(entry.entity_type):
            return True
        return operation == Operation.SNAPSHOT and entry.seed_to_local
    return registry.flows_to_cloud(entry.entity_type)


def _account_de(instance):
    conta = getattr(instance, "account", None)
    if conta is not None:
        return conta.pk
    # Account é a própria conta; Restaurant tem account_id direto.
    if type(instance).__name__ == "Account":
        return instance.pk
    perfil = getattr(instance, "profile", None)
    return getattr(perfil, "account_id", None)


def _criar_evento(origem, destino, account_id, entry, payload, operation, run):
    from apps.synchronization.services.outbox_sequencia import (
        MAX_TENTATIVAS_DE_SEQUENCIA,
        e_colisao_de_sequencia,
        realinhar_contador,
    )

    for tentativa in range(MAX_TENTATIVAS_DE_SEQUENCIA):
        try:
            return _gravar_evento(
                origem, destino, account_id, entry, payload, operation, run
            )
        except IntegrityError as erro:
            if not e_colisao_de_sequencia(erro):
                raise
            if tentativa == MAX_TENTATIVAS_DE_SEQUENCIA - 1:
                raise
            realinhar_contador(origem)
    return None


def _gravar_evento(origem, destino, account_id, entry, payload, operation, run):
    from apps.synchronization.models import SyncEvent

    with transaction.atomic():
        sequencia = origem.next_sequence()
        return SyncEvent.objects.create(
            account_id=account_id,
            source_node=origem,
            target_node=destino,
            run=run,
            direction=Direction.OUTBOUND,
            sequence=sequencia,
            entity_type=entry.entity_type,
            entity_id=payload["entity_id"],
            operation=operation,
            entity_version=payload["entity_version"],
            payload=payload,
            payload_checksum=crypto.checksum(payload),
            status=EventStatus.PENDING,
        )


def record_delete(instance):
    """Exclusão sincronizável. Preferimos `deleted_at`, mas quem chama decide."""
    return record(instance, operation=Operation.DELETE)


def pending_count(node=None):
    """Quantos eventos ainda não saíram. É a métrica que o Admin mostra."""
    from apps.synchronization.models import SyncEvent

    consulta = SyncEvent.objects.filter(
        direction=Direction.OUTBOUND,
        status__in=list(EventStatus.OUTBOUND_OPEN),
    )
    if node is not None:
        consulta = consulta.filter(source_node=node)
    return consulta.count()
