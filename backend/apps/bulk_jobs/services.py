import logging

from django.db import transaction
from django.utils import timezone

from apps.bulk_jobs.models import BulkJob
from apps.core.tenant import tenant_context

logger = logging.getLogger(__name__)


def enqueue_bulk_job(*, account, user, action, payload, total, dispatch=True):
    job = BulkJob.objects.create(
        account=account,
        requested_by=user,
        action=action,
        payload=payload,
        total=total,
    )
    if dispatch:
        dispatch_bulk_job(job)
    return job


def dispatch_bulk_job(job):
    from apps.bulk_jobs.tasks import run_bulk_job_task

    transaction.on_commit(lambda: _dispatch(run_bulk_job_task, job.pk))


def _dispatch(task, job_id):
    try:
        task.delay(str(job_id))
    except Exception:  # noqa: BLE001 — o beat recupera o job persistido
        logger.exception("Fila indisponível; operação %s será reenviada pelo agendador", job_id)


def queued_response(job):
    return {
        "id": str(job.pk),
        "status": BulkJob.QUEUED,
        "total": job.total,
        "message": "Lote recebido. Aguarde; o resultado aparecerá no sino de notificações.",
    }


def run_bulk_job(job_id, *, task_id=""):
    """Executa uma vez; o payload some ao terminar e o resultado fica auditável."""
    with transaction.atomic():
        job = BulkJob.all_objects.select_for_update().filter(pk=job_id).first()
        if job is None:
            return None
        if job.status == BulkJob.RUNNING and task_id and job.worker_task_id == task_id:
            pass  # a mesma entrega voltou depois da queda do processo
        elif job.status == BulkJob.QUEUED:
            job.status = BulkJob.RUNNING
            job.worker_task_id = task_id
            job.save(update_fields=["status", "worker_task_id", "updated_at"])
        else:
            return None

    try:
        with tenant_context(job.account):
            job.result = _handler(job)(job)
        job.status = BulkJob.DONE
    except Exception:  # noqa: BLE001 — a falha precisa virar estado e aviso ao operador
        logger.exception("Operação em lote %s falhou", job.pk)
        job.status = BulkJob.FAILED
        job.result = {"error": "O processamento parou por um erro inesperado."}
    job.payload = {}
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "result", "payload", "finished_at", "updated_at"])
    _notify_result(job)
    return job


def _handler(job):
    if job.action == BulkJob.COMMAND_RESET:
        from apps.restaurants.command_reset_job import run_command_reset_job
        return run_command_reset_job
    if job.action in {BulkJob.ORDER_CANCEL, BulkJob.ORDER_DELETE}:
        from apps.orders.bulk_jobs import run_order_bulk_job
        return run_order_bulk_job
    if job.action == BulkJob.INVOICE_RESEND:
        from apps.invoices.bulk import run_invoice_resend_job
        return run_invoice_resend_job
    if job.action in {BulkJob.INBOUND_RECONCILE, BulkJob.INBOUND_XML_IMPORT}:
        from apps.inbound_nfe.bulk_jobs import run_inbound_bulk_job
        return run_inbound_bulk_job
    raise ValueError(f"Ação em lote desconhecida: {job.action}")


def _notify_result(job):
    from apps.notifications.models import Notification
    from apps.notifications.services import notify

    title, body, has_warnings, url = _summary(job)
    notify(
        [job.requested_by],
        account=job.account,
        level=(Notification.LEVEL_WARNING if has_warnings else Notification.LEVEL_SUCCESS),
        title=title,
        body=body,
        url=url,
        entity="bulk_jobs.BulkJob",
        object_id=str(job.pk),
        metadata={"action": job.action, "result": _short_result(job.result)},
    )


def _summary(job):
    result = job.result
    if job.status == BulkJob.FAILED:
        return "Operação em lote não concluída", result["error"], True, ""
    if job.action == BulkJob.COMMAND_RESET:
        reset, skipped = result.get("reset", []), result.get("skipped", [])
        items = sum(item.get("items_removed", 0) for item in reset)
        return (
            "Zeramento de comandas concluído",
            _with_first_reason(
                f"{len(reset)} comanda(s) zerada(s), {items} item(ns) retirado(s), {len(skipped)} ignorada(s).",
                skipped,
            ),
            bool(skipped),
            "/comandas",
        )
    if job.action == BulkJob.ORDER_CANCEL:
        skipped = result.get("skipped", [])
        body = f"{result.get('cancelled', 0)} cancelado(s), {len(skipped)} ignorado(s)."
        return "Cancelamento em lote concluído", _with_first_reason(body, skipped), bool(skipped), "/pedidos"
    if job.action == BulkJob.ORDER_DELETE:
        skipped = result.get("skipped", [])
        body = f"{result.get('deleted', 0)} excluído(s), {len(skipped)} ignorado(s)."
        return "Exclusão em lote concluída", _with_first_reason(body, skipped), bool(skipped), "/pedidos"
    if job.action == BulkJob.INBOUND_RECONCILE:
        failed = result.get("errors", 0)
        body = f"{result.get('queried', 0)} consultada(s), {result.get('cancelled', 0)} cancelada(s), {failed} com erro."
        return "Conciliação SEFAZ concluída", body, bool(failed or result.get("cancelled")), "/inbound-nfe"
    if job.action == BulkJob.INBOUND_XML_IMPORT:
        failed = result.get("total_errors", 0)
        body = f"{result.get('total_processed', 0)} nota(s) processada(s), {failed} arquivo(s) com erro."
        return "Importação de XML concluída", body, bool(failed), "/inbound-nfe"
    failed = result.get("failed", 0)
    body = f"{result.get('resent', 0)} reenviada(s), {failed} com falha."
    return "Reenvio de NFC-e concluído", _with_first_reason(body, result.get("errors", [])), bool(failed), "/notas-fiscais"


def _with_first_reason(body, problems):
    if not problems:
        return body
    reason = problems[0].get("reason") or problems[0].get("message")
    return f"{body} Primeiro motivo: {reason}" if reason else body


def _short_result(result):
    shortened = dict(result)
    for field in ("reset", "skipped", "errors", "results"):
        if isinstance(shortened.get(field), list):
            shortened[field] = shortened[field][:20]
    return shortened
