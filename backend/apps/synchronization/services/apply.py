"""Aplica no domínio um evento que já está seguro na inbox.

Três garantias, nesta ordem:

1. **Idempotência.** O mesmo `event_id` duas vezes aplica uma vez só — e o
   reenvio depois de timeout responde ACK sem reaplicar (§18).
2. **Sem eco.** Tudo roda dentro de `applying_remote_event()`, então a
   gravação não gera evento de volta (§13.2).
3. **Ordem.** Quem chama entrega os eventos por sequência; uma dependência que
   ainda não chegou vira falha retentável, não perda.
"""
import logging

from django.db import IntegrityError, transaction

from apps.synchronization.constants import EventStatus, Operation
from apps.synchronization.services import adoption, conflicts, outbox, retry, serialization
from apps.synchronization.services.registry import registry
from django.utils import timezone

logger = logging.getLogger(__name__)


class DependencyMissing(Exception):
    """Falta um registro-pai. É retentável: o evento dele provavelmente vem a caminho."""


class IntegrityRejected(Exception):
    """O banco recusou a gravação, e retentar não vai mudar isso.

    Dois casos caem aqui: outra linha ocupa a mesma chave única e não pôde
    ceder o lugar (ver `adoption.py`), ou o payload viola outra regra do
    schema — um campo obrigatório que não veio, por exemplo.

    Os dois são estruturais: bater na fila até morrer só adia a descoberta.
    Viram conflito aberto, para alguém olhar.
    """


def apply_event(event):
    """Aplica um SyncEvent da inbox. Devolve True se mexeu no domínio."""
    if event.status in (EventStatus.APPLIED, EventStatus.ACKNOWLEDGED):
        return False  # idempotência: já passou por aqui

    entrada = registry.get(event.entity_type)
    if entrada is None:
        # Entidade desconhecida não derruba a conexão (§17): fica registrada e
        # segue a vida. Uma nuvem mais nova pode conhecer coisas que a loja não.
        _marcar_aplicado(event, nota=f"Entidade não registrada aqui: {event.entity_type}")
        return False

    try:
        with transaction.atomic(), outbox.applying_remote_event():
            mexeu = _aplicar(event, entrada)
            _marcar_aplicado(event)
        return mexeu
    except DependencyMissing as erro:
        retry.mark_failure(event, erro)
        return False
    except IntegrityRejected as erro:
        # Retentar não conserta violação de schema: quem decide é uma pessoa.
        # O evento sai da fila e vira conflito aberto.
        conflicts.register(
            event, local_instance=None, remote_payload=(event.payload or {}).get("fields", {}),
            local_version=0, remote_version=int(event.entity_version or 1),
        )
        _marcar_aplicado(event, nota=str(erro)[:2000])
        logger.error(
            "sync: o banco recusou %s/%s — %s", event.entity_type, event.entity_id, erro
        )
        return False
    except Exception as erro:  # noqa: BLE001 — qualquer falha vira retentativa
        logger.exception("sync: falha ao aplicar %s", event.event_id)
        retry.mark_failure(event, erro)
        return False


def _aplicar(event, entrada):
    model = entrada.model
    payload = event.payload or {}
    fields = payload.get("fields", {})
    remote_version = int(payload.get("entity_version") or event.entity_version or 1)

    existente = _encontrar(model, event.entity_id)

    if event.operation == Operation.DELETE:
        return _apagar(existente)

    decisao = conflicts.decide(
        event.entity_type,
        local_version=serialization.entity_version(existente) if existente else 0,
        remote_version=remote_version,
        receiving_node_type=event.target_node.node_type,
        local_exists=existente is not None,
        # A instância vai junto porque a decisão depende de ELA ter nascido
        # aqui ou ter vindo da sincronização — ver `_origem_vence_a_versao`.
        local_instance=existente,
    )
    if decisao == conflicts.IGNORAR:
        return False
    if decisao == conflicts.CONFLITO:
        conflicts.register(
            event,
            local_instance=existente,
            remote_payload=fields,
            local_version=serialization.entity_version(existente) if existente else 0,
            remote_version=remote_version,
        )
        return False

    if existente is not None and entrada.immutable:
        # Append-only: movimento de estoque, leitura de balança, auditoria.
        return False

    return _gravar(model, entrada, event, fields, existente)


def _encontrar(model, pk):
    """A linha com esta identidade, esteja ela visível ou não.

    O manager padrão de boa parte dos models daqui é filtrado — por tenant, por
    `deleted_at`, por conta ativa. Procurar só por ele faz uma linha que existe
    parecer ausente, e aí a aplicação tenta INSERIR um UUID que o banco já tem:
    erro de chave duplicada num caminho em que a resposta certa era atualizar.

    A ordem vai do mais específico ao mais cru: `_base_manager` é o único que o
    Django garante sem filtro nenhum.
    """
    for manager in (
        model._default_manager,
        getattr(model, "all_objects", None),
        model._base_manager,
    ):
        if manager is None:
            continue
        encontrado = manager.filter(pk=pk).first()
        if encontrado is not None:
            return encontrado
    return None


def _gravar(model, entrada, event, fields, existente):
    kwargs = serialization.deserialize(model, fields)
    kwargs.pop("id", None)
    for campo in entrada.local_only_fields:
        # O IP da impressora é da loja; a nuvem não tem como saber e não
        # pode zerar o que o técnico configurou lá.
        kwargs.pop(campo, None)
        kwargs.pop(f"{campo}_id", None)

    _validar_dependencias(model, kwargs)

    if existente is None:
        return _inserir(model, kwargs, event)

    return _atualizar(existente, kwargs)


def _atualizar(instancia, kwargs):
    """Grava só se algo mudou de verdade. Devolve True se mexeu.

    Reaplicar um registro idêntico não é inofensivo: cada `save()` mexe no
    `updated_at`, dispara os sinais do model e — num destino que também
    sincroniza — vira movimento para o outro lado. Numa carga inicial de
    centenas de registros que já estão iguais, isso é trabalho puro sem
    resultado nenhum.
    """
    mudou = [
        nome for nome, valor in kwargs.items()
        if not _igual(getattr(instancia, nome, None), valor)
    ]
    if not mudou:
        return False

    for nome in mudou:
        setattr(instancia, nome, kwargs[nome])
    instancia.save()
    return True


def _igual(atual, novo):
    """Comparação tolerante ao tipo que voltou da serialização.

    Um UUID chega como `str` no payload e vive como `UUID` na instância; o
    mesmo vale para Decimal e data. Na dúvida a resposta é "mudou" — gravar à
    toa custa uma escrita, dar um falso "igual" descarta um dado novo.
    """
    if atual == novo:
        return True
    if atual is None or novo is None:
        return False
    return str(atual) == str(novo)


def _inserir(model, kwargs, event):
    """Insere com a identidade da origem, resolvendo duplicata local se houver.

    A duplicata acontece quando o destino criou sozinho, por efeito colateral,
    a linha que a origem também manda — ver `services/adoption.py`.
    """
    try:
        with transaction.atomic():
            model(pk=event.entity_id, **kwargs).save(force_insert=True)
        return True
    except IntegrityError as erro:
        # Se a identidade JÁ existe, inserir nunca foi a operação certa —
        # atualizar é. Acontece quando a linha estava invisível na consulta
        # (manager filtrado, corrida entre dois eventos do mesmo registro) e é
        # o caso em que `try_adopt` não tem nada a fazer: não há disputa por
        # chave única, há o mesmo registro chegando de novo, possivelmente com
        # dados mais novos.
        ja_existe = model._base_manager.filter(pk=event.entity_id).first()
        if ja_existe is not None:
            mexeu = _atualizar(ja_existe, kwargs)
            logger.info(
                "sync: %s %s já existia — %s em vez de inserido",
                model.__name__, event.entity_id,
                "atualizado" if mexeu else "sem mudanças, ignorado",
            )
            return mexeu

        adotou, motivo = adoption.try_adopt(model, kwargs, event)
        if not adotou:
            raise IntegrityRejected(f"{erro} — {motivo}") from erro
        model(pk=event.entity_id, **kwargs).save(force_insert=True)
        return True


def _validar_dependencias(model, kwargs):
    """Chave estrangeira apontando para registro que ainda não chegou."""
    for campo in model._meta.concrete_fields:
        if not campo.is_relation or campo.attname not in kwargs:
            continue
        valor = kwargs[campo.attname]
        if valor is None:
            continue
        alvo = campo.related_model._default_manager
        existe = alvo.filter(pk=valor).exists()
        if not existe and hasattr(campo.related_model, "all_objects"):
            existe = campo.related_model.all_objects.filter(pk=valor).exists()
        if not existe:
            raise DependencyMissing(
                f"{model.__name__}.{campo.name} aponta para {campo.related_model.__name__} "
                f"{valor}, que ainda não existe aqui."
            )


def _apagar(existente):
    if existente is None:
        return False  # já não existia: idempotente
    existente.delete()  # soft delete quando o model tem deleted_at
    return True


def _marcar_aplicado(event, nota=""):
    event.status = EventStatus.APPLIED
    event.applied_at = timezone.now()
    event.next_attempt_at = None
    # Limpar o erro no sucesso não é cosmético. Um evento que falhou, foi
    # retentado e deu certo ficava APPLIED carregando a mensagem da primeira
    # tentativa — e quem fosse diagnosticar leria "Restaurant.created_by aponta
    # para User 10, que ainda não existe aqui" num restaurante que existe,
    # procurando um problema que já tinha se resolvido sozinho.
    event.last_error = nota
    event.save(update_fields=["status", "applied_at", "next_attempt_at", "last_error"])
