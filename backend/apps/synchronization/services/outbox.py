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
import threading

from django.db import transaction

from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.services import crypto, nodes, serialization
from apps.synchronization.services.registry import registry

logger = logging.getLogger(__name__)

#: Enquanto ligado, nada do que este processo grava vira evento novo. É o
#: `SET LOCAL app.sync_apply = '1'` do plano, na versão que funciona também no
#: SQLite do desenvolvimento: uma flag por thread, ligada só durante o apply.
_estado = threading.local()


def is_applying():
    return getattr(_estado, "applying", False)


class applying_remote_event:
    """Context manager que desliga a captura durante a aplicação de um evento.

    Sem isso, aplicar um produto vindo da nuvem geraria um evento de volta para
    a nuvem, que geraria outro de volta para a loja: o laço infinito que o §13.2
    manda evitar.

    Desliga os DOIS caminhos de captura: a flag por thread (que os signals
    consultam) e, no PostgreSQL, a variável `app.sync_apply` da transação (que
    a trigger consulta). Desligar só um deixaria o laço vivo pelo outro.
    """

    def __enter__(self):
        self.anterior = is_applying()
        _estado.applying = True
        # `SET LOCAL` só tem efeito DENTRO de uma transação: em autocommit o
        # PostgreSQL o aceita, emite um aviso e não faz nada. Se quem chamou
        # não abriu transação, a supressão da trigger sumiria em silêncio — e o
        # sintoma seria um laço de eco, descoberto muito depois. Então o bloco
        # é garantido aqui, e não confiado a quem chama.
        self._transacao = None
        if not transaction.get_connection().in_atomic_block:
            self._transacao = transaction.atomic()
            self._transacao.__enter__()
        self._marcar_sessao()
        return self

    def __exit__(self, tipo, valor, traco):
        _estado.applying = self.anterior
        if self._transacao is not None:
            self._transacao.__exit__(tipo, valor, traco)
        return False

    def _marcar_sessao(self):
        """`SET LOCAL app.sync_apply = '1'`. Morre com a transação.

        Falhar aqui não pode abortar a aplicação: sem PostgreSQL não há
        trigger, e a flag por thread já cobre os signals.
        """
        try:
            from apps.synchronization.services import triggers

            triggers.mark_apply_session()
        except Exception:  # noqa: BLE001
            logger.debug("sync: não foi possível marcar app.sync_apply", exc_info=True)


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

    if not _direcao_permitida(entry, origem):
        return []

    destinos = nodes.targets_for(origem, account_id)
    if not destinos:
        return []

    payload = serialization.build_payload(instance, entry, origin_node_id=origem.id)
    return [
        _criar_evento(origem, destino, account_id, entry, payload, operation, run)
        for destino in destinos
    ]


def _direcao_permitida(entry, origem):
    if nodes.is_cloud():
        return registry.flows_to_local(entry.entity_type)
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
