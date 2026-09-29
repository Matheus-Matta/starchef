"""Cancelamento da anotação de comanda e seu aviso à cozinha."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.orders.command_items import conclude_item
from apps.orders.command_kitchen import dispatch_command_batch
from apps.orders.item_cancellation import assert_pode_cancelar
from apps.orders.models import CommandItem


@transaction.atomic
def void_command_item(item, *, user, reason, authorized=False, authorized_by=None):
    """Cancela a anotação e imprime aviso se ela já foi produzida."""
    if not reason:
        raise ValidationError("Informe o motivo do cancelamento.")
    with tenant_context(item.account):
        item = (
            CommandItem.objects.select_related("command", "batch", "product")
            .select_for_update(of=("self",))
            .get(pk=item.pk)
        )
        if item.status in {CommandItem.STATUS_CANCELLED, CommandItem.STATUS_COMPED}:
            raise ValidationError("Este item já foi cancelado ou retirado da conta.")

        within_grace = item.status == CommandItem.STATUS_QUEUED
        if (
            within_grace
            and item.batch
            and item.batch.dispatch_at
            and item.batch.dispatch_at <= timezone.now()
        ):
            dispatch_command_batch(item.batch)
            item.refresh_from_db()
            within_grace = item.status == CommandItem.STATUS_QUEUED

        assert_pode_cancelar(item, authorized=authorized)
        was_dispatched = item.status not in {
            CommandItem.STATUS_PENDING,
            CommandItem.STATUS_QUEUED,
        }
        now = timezone.now()
        item.status = CommandItem.STATUS_CANCELLED
        item.void_reason = reason
        item.voided_at = now
        item.voided_by = user
        item.updated_by = user
        item.save(
            update_fields=[
                "status",
                "void_reason",
                "voided_at",
                "voided_by",
                "updated_by",
                "updated_at",
            ]
        )
        conclude_item(item, when=now, billed=False)
        _update_printing(
            item=item,
            user=user,
            reason=reason,
            within_grace=within_grace,
            was_dispatched=was_dispatched,
        )
        record_audit(
            action=AuditLog.ACTION_UPDATED,
            instance=item,
            actor=user,
            reason=reason,
            metadata={
                "event": "command_item_voided",
                **({"authorized_by": str(authorized_by.pk)} if authorized_by else {}),
            },
        )
    return item


def _update_printing(*, item, user, reason, within_grace, was_dispatched):
    if within_grace and item.batch_id:
        from apps.printers.command_kitchen import refresh_scheduled_command_jobs

        refresh_scheduled_command_jobs(batch=item.batch, user=user)
    elif was_dispatched:
        from apps.printers.command_kitchen import register_command_item_cancellation_jobs

        register_command_item_cancellation_jobs(item=item, user=user, reason=reason)
