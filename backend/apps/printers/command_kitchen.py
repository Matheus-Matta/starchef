"""Tickets de produção para a comanda que ainda não virou pedido."""

from decimal import Decimal
from html import escape

from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.printers.models import Printer, PrintJob
from apps.printers.services import (
    LARGURA_COMANDA,
    _kitchen_quantity,
    _kitchen_two_columns,
)


def _texto_da_rodada(*, batch, sector, items):
    command = batch.command
    total = sum((Decimal(item.quantity) for item in items), Decimal("0"))
    lines = [
        "NOVO PEDIDO".center(LARGURA_COMANDA),
        str(sector.name).upper().center(LARGURA_COMANDA)[:LARGURA_COMANDA],
        "-" * LARGURA_COMANDA,
        _kitchen_two_columns(
            f"COMANDA {command.code or command.number}",
            f"RODADA {batch.batch_number}",
        ),
        timezone.localtime(batch.sent_at).strftime("%d/%m/%Y %H:%M:%S"),
    ]
    if command.current_table_id:
        lines.append(f"MESA: {command.current_table.number}"[:LARGURA_COMANDA])
    if command.customer_name:
        lines.append(f"CLIENTE: {command.customer_name}"[:LARGURA_COMANDA])
    if batch.sent_by_id:
        atendente = batch.sent_by.get_full_name() or batch.sent_by.username
        lines.append(f"ATENDENTE: {atendente}"[:LARGURA_COMANDA])
    lines.append("-" * LARGURA_COMANDA)
    for item in items:
        produto = (
            f"{_kitchen_quantity(item.quantity)}x "
            f"{item.product.name}{item.variation_suffix}"
        )
        lines.append(produto[:LARGURA_COMANDA])
        for addon in item.addons.all():
            lines.append(f"  {addon.addon.name}"[:LARGURA_COMANDA])
        if item.customer_note:
            lines.append(f"  OBS: {item.customer_note}"[:LARGURA_COMANDA])
        lines.append("-" * LARGURA_COMANDA)
    lines.append(_kitchen_two_columns("TOTAL DE ITENS", _kitchen_quantity(total)))
    lines.extend([f"REF: {batch.serial}", ""])
    return "\n".join(lines)


def register_command_batch_print_jobs(*, batch, user, offline_printed=False):
    """Cria um ticket por setor para a rodada da comanda."""
    command = batch.command
    with tenant_context(command.account):
        items = list(
            batch.items.select_related("product__sector")
            .prefetch_related("addons__addon")
            .filter(status="queued")
            .order_by("launched_at")
        )
        by_sector = {}
        for item in items:
            sector = item.product.sector
            if sector is not None:
                by_sector.setdefault(sector.pk, [sector, []])[1].append(item)

        jobs = []
        for sector, sector_items in by_sector.values():
            printers = Printer.objects.filter(
                restaurant=command.restaurant, sector=sector, is_active=True
            ).order_by("name")
            text = _texto_da_rodada(
                batch=batch, sector=sector, items=sector_items
            )
            for printer in printers:
                status = (
                    PrintJob.STATUS_PRINTED
                    if offline_printed
                    else PrintJob.STATUS_SCHEDULED
                )
                job = PrintJob.objects.create(
                    account=command.account,
                    restaurant=command.restaurant,
                    branch=command.branch,
                    printer=printer,
                    job_type=PrintJob.TYPE_KITCHEN,
                    status=status,
                    printed_at=timezone.now() if offline_printed else None,
                    available_at=batch.dispatch_at,
                    payload={
                        "command_id": str(command.pk),
                        "batch_id": str(batch.pk),
                        "batch_number": batch.batch_number,
                        "batch_serial": str(batch.serial),
                        "sector_id": str(sector.pk),
                        "item_ids": [str(item.pk) for item in sector_items],
                        "text_content": text,
                        "offline_printed": offline_printed,
                    },
                    html_content=f"<pre>{escape(text)}</pre>",
                    printed_by=user,
                    created_by=user,
                    updated_by=user,
                )
                jobs.append(job)
                record_audit(
                    action=AuditLog.ACTION_PRINTED,
                    instance=job,
                    actor=user,
                    metadata={"job_type": job.job_type, "batch": batch.batch_number},
                )
        return jobs


def refresh_scheduled_command_jobs(*, batch, user):
    """Refaz o ticket ainda em carência depois de um cancelamento."""
    now = timezone.now()
    PrintJob.objects.filter(
        payload__batch_id=str(batch.pk), status=PrintJob.STATUS_SCHEDULED
    ).update(status=PrintJob.STATUS_CANCELLED, updated_at=now)
    if not batch.items.filter(status="queued").exists():
        batch.status = batch.STATUS_CANCELLED
        batch.save(update_fields=["status", "updated_at"])
        return []
    return register_command_batch_print_jobs(batch=batch, user=user)


def register_command_item_cancellation_jobs(*, item, user, reason):
    """Cria o aviso na mesma impressora que recebeu a rodada original."""
    originals = PrintJob.objects.filter(
        job_type=PrintJob.TYPE_KITCHEN,
        payload__batch_id=str(item.batch_id),
    ).exclude(status=PrintJob.STATUS_CANCELLED)
    jobs = []
    for original in originals:
        if str(item.pk) not in {str(value) for value in original.payload.get("item_ids", [])}:
            continue
        exists = PrintJob.objects.filter(
            original_job=original,
            job_type=PrintJob.TYPE_KITCHEN_CANCEL,
            payload__cancelled_command_item_id=str(item.pk),
        ).exists()
        if exists:
            continue
        command = item.command
        text = "\n".join(
            [
                "CANCELAMENTO".center(LARGURA_COMANDA),
                f"COMANDA {command.code or command.number}".center(LARGURA_COMANDA),
                f"ORIGINAL {original.serial}".center(LARGURA_COMANDA),
                "-" * LARGURA_COMANDA,
                f"CANCELAR {_kitchen_quantity(item.quantity)}x "
                f"{item.product.name}{item.variation_suffix}"[:LARGURA_COMANDA],
                f"MOTIVO: {reason}"[:LARGURA_COMANDA],
                f"SOLICITADO POR: {user.get_full_name() or user.username}"[:LARGURA_COMANDA],
                "-" * LARGURA_COMANDA,
                "FIM DO CANCELAMENTO".center(LARGURA_COMANDA),
                "",
            ]
        )
        job = PrintJob.objects.create(
            account=item.account,
            restaurant=item.restaurant,
            branch=item.branch,
            printer=original.printer,
            original_job=original,
            job_type=PrintJob.TYPE_KITCHEN_CANCEL,
            status=PrintJob.STATUS_RENDERED,
            available_at=timezone.now(),
            payload={
                "command_id": str(command.pk),
                "cancelled_command_item_id": str(item.pk),
                "reason": reason,
                "text_content": text,
            },
            html_content=f"<pre>{escape(text)}</pre>",
            printed_by=user,
            created_by=user,
            updated_by=user,
        )
        jobs.append(job)
        record_audit(
            action=AuditLog.ACTION_PRINTED,
            instance=job,
            actor=user,
            reason=reason,
            metadata={"job_type": job.job_type, "command_item": str(item.pk)},
        )
    return jobs
