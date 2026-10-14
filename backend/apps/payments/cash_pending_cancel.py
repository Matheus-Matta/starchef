"""Desistir do que espera a senha do caixa: fechamento, sangria e suprimento.

Autorizar (`approve_cash_operation`) confirma o gesto; isto o DESFAZ. Por isso
não pede senha: não libera dinheiro nenhum, só devolve a sessão ao estado de
antes — o fechamento volta a ser caixa aberto e a movimentação vira cancelada,
fora do saldo esperado.

Só o dono da sessão desiste, pela mesma regra do fechar e do sangrar: outro
operador mexendo no caixa alheio passa pela transferência gerencial.
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.payments.models import CashMovement, CashRegister
from apps.payments.terminals import assert_session_owner


class NadaPendente(ValidationError):
    """Não há o que desistir: o estado já mudou. A rota responde 409."""


@transaction.atomic
def cancel_pending_cash_operation(*, cash_register, user, movement_id=None, terminal=None, installation_id=""):
    with tenant_context(cash_register.account):
        # Relido DEPOIS do lock: aprovado no outro terminal enquanto este
        # decidia desistir, o gesto já valeu e não se desfaz por aqui.
        cash_register = (
            CashRegister.objects.select_related("opened_by", "opened_terminal", "cash_station")
            .select_for_update(of=("self",))
            .get(pk=cash_register.pk)
        )
        assert_session_owner(cash_register, user=user, terminal=terminal, installation_id=installation_id)
        if movement_id:
            return _cancelar_movimentacao(cash_register, movement_id, user)
        return _reabrir_fechamento(cash_register, user)


def _cancelar_movimentacao(cash_register, movement_id, user):
    movement = (
        CashMovement.objects.select_for_update()
        .filter(pk=movement_id, cash_register=cash_register)
        .first()
    )
    if movement is None or movement.status != "pending":
        raise NadaPendente("Esta movimentação não está mais aguardando autorização.")
    # `save()` e não `update()`: sem o signal a nuvem nunca fica sabendo.
    movement.status = "cancelled"
    movement.updated_by = user
    movement.save(update_fields=["status", "updated_by", "updated_at"])
    record_audit(
        action=AuditLog.ACTION_CANCELLED, instance=movement, actor=user,
        metadata={"event": f"{movement.movement_type}_cancelled_before_approval"},
    )
    return movement


def _reabrir_fechamento(cash_register, user):
    if cash_register.status != CashRegister.STATUS_PENDING_APPROVAL or cash_register.pending_operation != "closing":
        raise NadaPendente("Não há fechamento aguardando autorização neste caixa.")
    cash_register.status = CashRegister.STATUS_OPEN
    cash_register.pending_operation = ""
    cash_register.actual_amount = None
    cash_register.difference_amount = 0
    cash_register.closed_by = None
    cash_register.closed_at = None
    cash_register.closed_terminal = None
    cash_register.closed_terminal_label = ""
    cash_register.updated_by = user
    cash_register.save()
    # O lançamento de fechamento sai junto: o caixa não fechou, e o relatório
    # do turno mostraria dois fechamentos quando ele fechar de verdade.
    for fechamento in cash_register.movements.select_for_update().filter(
        movement_type=CashMovement.TYPE_CLOSING, status="approved"
    ):
        fechamento.status = "cancelled"
        fechamento.updated_by = user
        fechamento.save(update_fields=["status", "updated_by", "updated_at"])
    record_audit(
        action=AuditLog.ACTION_UPDATED, instance=cash_register, actor=user,
        metadata={"event": "close_cash_cancelled_before_approval"},
    )
    return cash_register
