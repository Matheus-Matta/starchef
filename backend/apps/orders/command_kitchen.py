"""Mandar para a produção o que foi anotado na comanda.

É o MESMO gesto do pedido — uma rodada, um número, um ticket com `REF:`, a
carência do restaurante segurando tudo até `dispatch_at` vencer. O que muda é
só o dono: `CommandBatch` em vez de `OrderBatch`.

O estado que este módulo grava é o que, mais tarde, o item do pedido HERDA ao
ser cobrado (`command_billing._para_item_de_pedido`). É isso que impede a
picanha de voltar para o forno às 22h porque a conta só foi fechada então.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.core.audit import record_audit
from apps.orders.models import CommandBatch, CommandItem


@transaction.atomic
def send_command_to_kitchen(command, user, *, client_batch_serial=None, offline_printed=False, only=None):
    """Manda a rodada pendente desta comanda para a produção. Devolve o lote.

    `only` restringe a rodada a esses itens: a balança manda o prato que pesou,
    e não o que o garçom anotou e ainda não decidiu mandar.

    `client_batch_serial`/`offline_printed` existem para o PDV que já imprimiu
    localmente porque a rede estava fora: o serial garante que o `REF:` do
    ticket impresso bate com este lote, e a flag evita um segundo ticket.
    """
    import uuid

    with tenant_context(command.account):
        pendentes = CommandItem.objects.filter(
            command_id=command.pk,
            command_status=CommandItem.STATUS_PENDENTE,
            status=CommandItem.STATUS_PENDING,
        )
        if only is not None:
            pendentes = pendentes.filter(pk__in=[i.pk for i in only])
        itens = list(pendentes.select_related("product"))
        if not itens:
            raise ValidationError("Não há itens pendentes para enviar à cozinha.")

        agora = timezone.now()
        # Carência do restaurante: a rodada nasce agendada e só chega ao KDS e à
        # impressora quando `dispatch_at` vencer. Até lá, cancelar é de graça —
        # nada chegou à produção. Comanda já impressa no terminal não espera: o
        # papel já saiu.
        carencia = int(getattr(command.restaurant, "cancellation_grace_seconds", 0) or 0)
        if offline_printed:
            carencia = 0
        dispatch_at = agora + timedelta(seconds=carencia) if carencia > 0 else agora

        serial = None
        if client_batch_serial:
            try:
                serial = uuid.UUID(str(client_batch_serial))
            except (ValueError, AttributeError, TypeError):
                serial = None

        ultimo = CommandBatch.objects.filter(command_id=command.pk).aggregate(
            value=Max("batch_number")
        )["value"] or 0
        lote = CommandBatch.objects.create(
            account=command.account,
            restaurant=command.restaurant,
            branch=command.branch,
            command=command,
            batch_number=ultimo + 1,
            status=CommandBatch.STATUS_SCHEDULED,
            sent_at=agora,
            dispatch_at=dispatch_at,
            sent_by=user,
            created_by=user,
            updated_by=user,
            **({"serial": serial} if serial else {}),
        )

        CommandItem.objects.filter(pk__in=[i.pk for i in itens]).update(
            status=CommandItem.STATUS_QUEUED,
            batch=lote,
            sent_to_kitchen_at=None,
            updated_by=user,
            updated_at=agora,
        )

        record_audit(
            action=AuditLog.ACTION_UPDATED,
            instance=command,
            actor=user,
            metadata={
                "event": "command_kitchen_dispatch_requested",
                "batch": lote.batch_number,
                "batch_serial": str(lote.serial),
                "dispatch_at": dispatch_at.isoformat(),
                "immediate": carencia == 0,
                "grace_seconds": carencia,
                "items": len(itens),
            },
        )

        from apps.printers.command_kitchen import register_command_batch_print_jobs

        register_command_batch_print_jobs(
            batch=lote, user=user, offline_printed=offline_printed
        )

        dispatch_command_batch(lote, now=agora)
    return lote


@transaction.atomic
def dispatch_command_batch(batch, *, now=None):
    """Solta a rodada agendada para o KDS e para as impressoras.

    Chamada logo após o envio (quando não há carência) e pela varredura que
    vence as agendadas. Repetir é inofensivo: só a rodada AGENDADA e já vencida
    faz alguma coisa.
    """
    agora = now or timezone.now()
    with tenant_context(batch.account):
        batch = (
            CommandBatch.objects.select_related("command__restaurant", "sent_by")
            # `sent_by` é anulável e o PostgreSQL recusa FOR UPDATE no lado
            # anulável do LEFT JOIN a menos que a trava seja restrita.
            .select_for_update(of=("self",)).get(pk=batch.pk)
        )
        if batch.status != CommandBatch.STATUS_SCHEDULED:
            return batch
        if batch.dispatch_at and batch.dispatch_at > agora:
            return batch

        CommandItem.objects.filter(
            batch_id=batch.pk, status=CommandItem.STATUS_QUEUED
        ).update(
            status=CommandItem.STATUS_SENT,
            sent_to_kitchen_at=agora,
            updated_at=agora,
        )
        batch.status = CommandBatch.STATUS_SENT
        batch.save(update_fields=["status", "updated_at"])

        from apps.printers.models import PrintJob

        PrintJob.objects.filter(
            payload__batch_id=str(batch.pk),
            status=PrintJob.STATUS_SCHEDULED,
        ).update(status=PrintJob.STATUS_RENDERED, available_at=agora, updated_at=agora)
    return batch


def dispatch_due_command_batches(*, account_id=None, restaurant_id=None, now=None):
    """Libera as rodadas de comanda cuja carência terminou."""
    now = now or timezone.now()
    due = CommandBatch.all_objects.filter(
        status=CommandBatch.STATUS_SCHEDULED,
        dispatch_at__lte=now,
        deleted_at__isnull=True,
    )
    if account_id:
        due = due.filter(account_id=account_id)
    if restaurant_id:
        due = due.filter(restaurant_id=restaurant_id)
    batch_ids = list(due.values_list("id", flat=True)[:500])
    for batch_id in batch_ids:
        batch = CommandBatch.all_objects.select_related("account").get(pk=batch_id)
        dispatch_command_batch(batch, now=now)
    return len(batch_ids)


def void_command_item(item, *, user, reason, authorized=False, authorized_by=None):
    """Mantém o caminho público antigo após separar a regra de cancelamento."""
    from apps.orders.command_item_void import void_command_item as cancel_item

    return cancel_item(
        item,
        user=user,
        reason=reason,
        authorized=authorized,
        authorized_by=authorized_by,
    )
