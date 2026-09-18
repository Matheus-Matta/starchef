"""Carga total e de dados essenciais: encher um banco local vazio.

O que torna a carga retomável é ela ser feita de eventos comuns na outbox. Se
o worker morrer no meio, o que já foi gerado continua lá e o dispatcher segue
de onde parou — não há "refazer do zero" nem estado só na memória do processo.
"""
import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.synchronization.constants import Operation, RunStatus, RunType
from apps.synchronization.models import SyncRun
from apps.synchronization.services import guard, nodes, outbox
from apps.synchronization.services.registry import registry

logger = logging.getLogger(__name__)


class BootstrapBusy(RuntimeError):
    """Já existe uma carga em andamento para este nó (§14.2)."""


def start_run(*, target_node, run_type=RunType.BOOTSTRAP, user=None, ip=None, reason=""):
    """Cria o SyncRun. Duas cargas simultâneas no mesmo nó são recusadas."""
    guard.ensure_enabled()
    origem = nodes.self_node()

    em_andamento = SyncRun.objects.filter(
        target_node=target_node, status__in=list(RunStatus.BUSY)
    ).first()
    if em_andamento is not None:
        raise BootstrapBusy(
            f"A carga {em_andamento.id} ainda está em {em_andamento.status}."
        )

    return SyncRun.objects.create(
        account_id=target_node.account_id,
        source_node=origem,
        target_node=target_node,
        run_type=run_type,
        status=RunStatus.PENDING,
        snapshot_cursor=origem.sequence_counter,
        initiated_by=user,
        initiated_ip=ip,
        reason=reason[:255],
    )


def cancel_running(target_node, *, motivo=""):
    """Cancela as cargas em andamento de um nó. Devolve quantas.

    Existe para a rematrícula: uma loja que reinstalou está começando de novo,
    e a carga anterior — que ninguém mais vai receber — não pode bloquear a
    nova para sempre. Os eventos já gerados continuam na outbox; o que muda é
    só o estado do SyncRun.
    """
    return SyncRun.objects.filter(
        target_node=target_node, status__in=list(RunStatus.BUSY)
    ).update(
        status=RunStatus.CANCELLED,
        completed_at=timezone.now(),
        error=motivo or "Cancelada por uma nova carga do mesmo nó.",
    )


def build_manifest(run):
    """Quantos registros de cada entidade a carga vai levar.

    O manifesto é o que permite validar o fim: totais por entidade conferidos
    contra o que chegou do outro lado.
    """
    somente_essenciais = run.run_type == RunType.BOOTSTRAP
    manifesto, total = {}, 0
    for entrada in registry.ordered(bootstrap_only=somente_essenciais):
        if not _flui_para(entrada, run):
            continue
        quantidade = _queryset(entrada, run).count()
        manifesto[entrada.entity_type] = quantidade
        total += quantidade

    run.manifest = manifesto
    run.total_entities = len(manifesto)
    run.total_records = total
    run.status = RunStatus.PREPARING
    run.started_at = run.started_at or timezone.now()
    run.save(update_fields=[
        "manifest", "total_entities", "total_records", "status", "started_at",
    ])
    return manifesto


def _flui_para(entrada, run):
    if run.target_node.node_type == "LOCAL":
        # `seed_to_local` abre exceção para o estado vivo do salão: pedido
        # aberto e sessão de caixa sobem no dia a dia, mas precisam DESCER uma
        # vez, senão a loja assume a operação com as mesas ocupadas e nenhuma
        # comanda para atender.
        return registry.flows_to_local(entrada.entity_type) or entrada.seed_to_local
    return registry.flows_to_cloud(entrada.entity_type)


def _queryset(entrada, run):
    """Os registros da conta da carga — e só os dela."""
    model = entrada.model
    gerente = getattr(model, "all_objects", model._default_manager)
    consulta = gerente.all()
    campos = {c.name for c in model._meta.concrete_fields}

    if "account" in campos:
        consulta = consulta.filter(account_id=run.account_id)
    elif model.__name__ == "Account":
        consulta = consulta.filter(pk=run.account_id)
    elif model.__name__ == "User":
        consulta = consulta.filter(profile__account_id=run.account_id)

    if entrada.scope == "store" and run.target_node.restaurant_id and "restaurant" in campos:
        consulta = consulta.filter(restaurant_id=run.target_node.restaurant_id)
    if entrada.essential_filter and run.run_type == RunType.BOOTSTRAP:
        # Só na carga ESSENCIAL. Ali a loja leva o que precisa para abrir a
        # porta: cadastros mais o estado vivo do salão — a comanda aberta, o
        # caixa em turno. "Sincronizar tudo" ignora este filtro de propósito,
        # porque ali a promessa é trazer todos os dados da conta.
        consulta = consulta.filter(**entrada.essential_filter)
    return consulta.order_by("pk")


def generate_events(run, *, chunk=500):
    """Gera os eventos da carga, entidade por entidade, na ordem topológica.

    Cada entidade é uma transação própria: interromper no meio deixa o que já
    passou gravado e retomável, sem uma transação gigante segurando o banco.
    """
    guard.ensure_enabled()
    run.status = RunStatus.RUNNING
    run.save(update_fields=["status"])

    somente_essenciais = run.run_type == RunType.BOOTSTRAP
    for entrada in registry.ordered(bootstrap_only=somente_essenciais):
        if not _flui_para(entrada, run):
            continue
        _gerar_entidade(run, entrada, chunk)

    run.status = RunStatus.VALIDATING
    run.current_entity = ""
    run.save(update_fields=["status", "current_entity"])
    return run


def _gerar_entidade(run, entrada, chunk):
    run.current_entity = entrada.entity_type
    run.save(update_fields=["current_entity"])

    consulta = _queryset(entrada, run)
    processados = 0
    for instancia in consulta.iterator(chunk_size=chunk):
        try:
            with transaction.atomic():
                outbox.record(instancia, operation=Operation.SNAPSHOT, run=run, force=True)
            processados += 1
        except Exception as erro:  # noqa: BLE001 — um registro ruim não para a carga
            logger.exception("sync: falha no snapshot de %s", entrada.entity_type)
            run.failed_records += 1
            run.error = str(erro)[:2000]
        if processados % chunk == 0:
            _progresso(run, processados)
            processados = 0
    _progresso(run, processados)
    run.processed_entities += 1
    run.save(update_fields=["processed_entities", "failed_records", "error"])


def _progresso(run, quantidade):
    """Soma no banco com F(): o Admin lê o progresso enquanto a carga roda."""
    if not quantidade:
        return
    SyncRun.objects.filter(pk=run.pk).update(
        processed_records=F("processed_records") + quantidade
    )
    run.processed_records += quantidade


def finish(run, *, error=""):
    run.status = RunStatus.FAILED if error else RunStatus.COMPLETED
    run.error = error[:2000]
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "error", "completed_at"])
    return run
