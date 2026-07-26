"""Tipos concretos de notificação — reutilizáveis e centralizados.

Cada classe descreve UM evento notificável do domínio. Os sinais (signals.py)
apenas instanciam e chamam `dispatch(...)`.
"""
from apps.notifications.models import Notification
from apps.notifications.services import NotificationType, managers_of_account


class CashDivergenceNotification(NotificationType):
    """Divergência de caixa aguardando aprovação gerencial."""

    category = Notification.CATEGORY_CASH
    level = Notification.LEVEL_WARNING

    def build(self, *, register, **_):
        operation = "abertura" if register.pending_operation == "opening" else "fechamento"
        return {
            "title": "Divergência de caixa aguardando aprovação",
            "body": f"O caixa “{register.station}” teve divergência no {operation} e precisa de aprovação gerencial.",
            "url": "/caixa",
            "entity": "payments.CashRegister",
            "object_id": str(register.pk),
            "metadata": {"difference_amount": str(register.difference_amount)},
        }

    def recipients(self, *, register, **_):
        # Não notifica o próprio operador que abriu/fechou — outro gerente aprova.
        return managers_of_account(register.account_id, exclude_user_id=register.opened_by_id)


class WithdrawalPendingNotification(NotificationType):
    """Sangria registrada e pendente de aprovação por outro gerente."""

    category = Notification.CATEGORY_CASH
    level = Notification.LEVEL_WARNING

    def build(self, *, movement, **_):
        amount = abs(movement.amount)
        return {
            "title": "Sangria aguardando aprovação",
            "body": f"Uma sangria de R$ {amount} foi registrada e aguarda aprovação gerencial.",
            "url": "/caixa",
            "entity": "payments.CashMovement",
            "object_id": str(movement.pk),
            "metadata": {"amount": str(amount), "reason": movement.reason},
        }

    def recipients(self, *, movement, **_):
        return managers_of_account(movement.account_id, exclude_user_id=movement.operator_id)
