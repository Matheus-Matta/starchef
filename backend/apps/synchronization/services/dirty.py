"""Transforma as marcas da trigger em eventos de verdade.

A trigger anota `(tabela, id, operação)`. Aqui o Python busca a linha, serializa
com o MESMO código de sempre e grava o evento pela outbox normal. É o que faz
uma escrita em massa — `QuerySet.update`, `bulk_create`, SQL direto — chegar ao
outro lado sem que ninguém tenha lembrado de chamar nada.

O atraso é a diferença: pelo signal o evento nasce na mesma transação do dado;
por aqui ele nasce alguns segundos depois. Isso é aceitável para a rede de
segurança e **não** é aceitável para o caminho principal — por isso o signal
continua existindo, e esta tarefa só recolhe o que escapou.
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.synchronization.constants import Operation
from apps.synchronization.models import SyncDirty
from apps.synchronization.services import outbox
from apps.synchronization.services.registry import registry

logger = logging.getLogger(__name__)

MAX_POR_EXECUCAO = 500


def _por_tabela():
    """`db_table -> entrada do catálogo`, montado uma vez por execução."""
    return {entrada.model._meta.db_table: entrada for entrada in registry.ordered()}


def process(limite=MAX_POR_EXECUCAO):
    """Converte marcas pendentes em eventos. Devolve `(convertidas, ignoradas)`."""
    pendentes = SyncDirty.objects.filter(processed_at__isnull=True).order_by("changed_at")[:limite]
    if not pendentes:
        return 0, 0

    catalogo = _por_tabela()
    convertidas = ignoradas = 0
    for marca in pendentes:
        try:
            criou = _converter(marca, catalogo)
        except Exception as erro:  # noqa: BLE001 — uma marca ruim não para a fila
            logger.exception("sync-dirty: falha ao converter %s", marca.id)
            marca.error = str(erro)[:2000]
            marca.processed_at = timezone.now()
            marca.save(update_fields=["error", "processed_at"])
            ignoradas += 1
            continue
        convertidas += 1 if criou else 0
        ignoradas += 0 if criou else 1

    if convertidas:
        logger.info("sync-dirty: %s marca(s) viraram evento", convertidas)
    return convertidas, ignoradas


def _converter(marca, catalogo):
    entrada = catalogo.get(marca.table_name)
    if entrada is None:
        return _encerrar(marca, "tabela não está no catálogo")

    if _ja_tem_evento(entrada.entity_type, marca):
        # O signal já pegou esta mesma gravação. O caminho normal e a rede de
        # segurança se sobrepõem de propósito; o que não pode é gerar dois
        # eventos para a mesma mudança.
        return _encerrar(marca, "já coberto pelo signal")

    model = entrada.model
    gerente = getattr(model, "all_objects", model._default_manager)
    instancia = gerente.filter(pk=marca.row_id).first()
    if instancia is None:
        return _encerrar(marca, "linha não existe mais")

    operacao = marca.operation if marca.operation in dict(Operation.CHOICES) else Operation.UPSERT
    with transaction.atomic():
        eventos = outbox.record(instancia, operation=operacao)
        marca.processed_at = timezone.now()
        marca.event = eventos[0] if eventos else None
        marca.save(update_fields=["processed_at", "event"])
    return bool(eventos)


def _ja_tem_evento(entity_type, marca):
    """Existe evento para esta linha criado depois da marca?"""
    from apps.synchronization.models import SyncEvent

    return SyncEvent.objects.filter(
        entity_type=entity_type,
        entity_id=str(marca.row_id),
        created_at__gte=marca.changed_at,
    ).exists()


def _encerrar(marca, motivo):
    marca.processed_at = timezone.now()
    marca.error = motivo
    marca.save(update_fields=["processed_at", "error"])
    return False


def prune(dias=7):
    """Marcas já processadas viram lixo rápido: uma por linha escrita."""
    corte = timezone.now() - timezone.timedelta(days=dias)
    apagadas, _ = SyncDirty.objects.filter(
        processed_at__isnull=False, processed_at__lt=corte
    ).delete()
    return apagadas


def pending_count():
    return SyncDirty.objects.filter(processed_at__isnull=True).count()
