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
from django.db.models import Max
from django.utils import timezone

from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.core.audit import record_audit
from apps.orders.models import CommandBatch, CommandItem


def send_command_to_kitchen(command, user, *, client_batch_serial=None, offline_printed=False):
    """Manda a rodada pendente desta comanda para a produção. Devolve o lote.

    `client_batch_serial`/`offline_printed` existem para o PDV que já imprimiu
    localmente porque a rede estava fora: o serial garante que o `REF:` do
    ticket impresso bate com este lote, e a flag evita um segundo ticket.
    """
    import uuid

    with tenant_context(command.account):
        itens = list(
            CommandItem.objects.filter(
                command_id=command.pk,
                command_status=CommandItem.STATUS_PENDENTE,
                status=CommandItem.STATUS_PENDING,
            ).select_related("product")
        )
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

        dispatch_command_batch(lote, now=agora)
    return lote


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
    return batch


def void_command_item(item, *, user, reason):
    """Cancela uma anotação. Sai da comanda como PERDA, não como venda.

    Item que já foi para a produção é outra conversa: sai um cupom de
    cancelamento na impressora do setor, e é por isso que o operador precisa
    ser avisado ANTES — ele descobriria pelo barulho da impressora.
    """
    from apps.orders.command_items import conclude_item

    if not reason:
        raise ValidationError("Informe o motivo do cancelamento.")
    with tenant_context(item.account):
        agora = timezone.now()
        item.status = CommandItem.STATUS_CANCELLED
        item.void_reason = reason
        item.voided_at = agora
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
        conclude_item(item, when=agora, billed=False)
        record_audit(
            action=AuditLog.ACTION_UPDATED,
            instance=item,
            actor=user,
            reason=reason,
            metadata={"event": "command_item_voided"},
        )
    return item
