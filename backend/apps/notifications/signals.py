"""Sinais que registram notificações a partir de eventos do domínio.

Conectados no `NotificationsConfig.ready()`. A entrega em si (WS) é feita pelos
serviços; aqui só decidimos QUANDO notificar, de forma idempotente.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.payments.models import CashMovement, CashRegister
from apps.notifications.models import Notification
from apps.notifications.types import CashDivergenceNotification, WithdrawalPendingNotification


@receiver(post_save, sender=CashRegister, dispatch_uid="notif_cash_register_divergence")
def on_cash_register_saved(sender, instance, **kwargs):
    if instance.status != CashRegister.STATUS_PENDING_APPROVAL:
        return
    # Idempotência: evita duplicar a cada save enquanto a divergência não é tratada.
    already = Notification.all_objects.filter(
        entity="payments.CashRegister",
        object_id=str(instance.pk),
        category=Notification.CATEGORY_CASH,
        is_read=False,
        deleted_at__isnull=True,
    ).exists()
    if already:
        return
    CashDivergenceNotification().dispatch(account=instance.account, register=instance)


@receiver(post_save, sender=CashMovement, dispatch_uid="notif_cash_withdrawal_pending")
def on_cash_movement_saved(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.movement_type != CashMovement.TYPE_WITHDRAWAL or instance.status != "pending":
        return
    WithdrawalPendingNotification().dispatch(account=instance.account, movement=instance)
