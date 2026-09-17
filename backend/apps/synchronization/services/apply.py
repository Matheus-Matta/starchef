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

    existente = model._default_manager.filter(pk=event.entity_id).first()
    if existente is None and hasattr(model, "all_objects"):
        existente = model.all_objects.filter(pk=event.entity_id).first()

    if event.operation == Operation.DELETE:
        return _apagar(existente)

    decisao = conflicts.decide(
        event.entity_type,
        local_version=serialization.entity_version(existente) if existente else 0,
        remote_version=remote_version,
        receiving_node_type=event.target_node.node_type,
        local_exists=existente is not None,
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

    for nome, valor in kwargs.items():
        setattr(existente, nome, valor)
    existente.save()
    return True


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
    if nota:
        event.last_error = nota
    event.save(update_fields=["status", "applied_at", "next_attempt_at", "last_error"])
