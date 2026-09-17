"""Administrative recovery operations for cash-register sessions."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.access import is_tenant_admin
from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.payments.models import CashRegister
from apps.payments.terminals import operator_label, terminal_label_of


@transaction.atomic
def force_release_cash_session(*, cash_register, administrator, reason):
    """Cancel an orphaned session so its station and operator can be reused.

    This deliberately does not pretend that the drawer was counted. A normal
    close records an actual amount; administrative recovery marks the session
    as cancelled and preserves the event in the audit trail.
    """
    if not is_tenant_admin(administrator):
        raise ValidationError("Somente um administrador da conta pode forçar a liberação do caixa.")

    reason = str(reason or "").strip()
    if not reason:
        raise ValidationError("Informe a justificativa da liberação administrativa.")

    with tenant_context(cash_register.account):
        cash_register = (
            CashRegister.objects.select_related(
                "opened_by", "opened_terminal", "cash_station", "restaurant"
            )
            .select_for_update(of=("self",))
            .get(pk=cash_register.pk)
        )
        if cash_register.is_finished:
            raise ValidationError("Esta sessão já foi finalizada e não bloqueia mais o caixa.")

        previous_status = cash_register.status
        pending_movements = list(cash_register.movements.filter(status="pending"))
        now = timezone.now()
        for movement in pending_movements:
            movement.status = "cancelled"
            movement.metadata = {
                **(movement.metadata or {}),
                "event": "cancelled_by_cash_session_force_release",
                "administrative_reason": reason,
            }
            movement.updated_by = administrator
            movement.save(update_fields=["status", "metadata", "updated_by", "updated_at"])

        expected = cash_register.movements.filter(status="approved").aggregate(
            value=Sum("amount")
        )["value"] or Decimal("0.00")
        cash_register.expected_amount = expected
        cash_register.actual_amount = None
        cash_register.difference_amount = Decimal("0.00")
        cash_register.status = CashRegister.STATUS_CANCELLED
        cash_register.pending_operation = ""
        cash_register.closed_by = administrator
        cash_register.closed_at = now
        cash_register.closed_terminal = None
        cash_register.closed_terminal_label = ""
        cash_register.approved_by = administrator
        cash_register.approved_at = now
        cash_register.approval_reason = reason
        cash_register.updated_by = administrator
        cash_register.save()

        record_audit(
            action=AuditLog.ACTION_CANCELLED,
            instance=cash_register,
            actor=administrator,
            reason=reason,
            metadata={
                "event": "cash_session_force_released",
                "previous_status": previous_status,
                "previous_operator": operator_label(cash_register.opened_by),
                "previous_terminal": terminal_label_of(cash_register),
                "cancelled_pending_movements": len(pending_movements),
            },
        )
        return cash_register
