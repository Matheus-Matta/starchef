"""Preenche quem/quando/como cancelou a partir do AuditLog.

Ate aqui o pedido so guardava `cancel_reason`; quem pediu, quem liberou e o
instante viviam no metadata da auditoria (`event=order_cancelled`) e do item
(`event=order_item_cancelled`). O relatorio de cancelamentos le das colunas
novas, entao o historico precisa subir para elas uma vez. Idempotente: so
mexe em linhas ainda vazias. Sem auditoria correspondente, `cancelled_at`
cai no `updated_at` do pedido (a ultima gravacao de um cancelado e o proprio
cancelamento) e a autorizacao fica em branco.
"""

from django.conf import settings
from django.db import migrations


def backfill(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")
    AuditLog = apps.get_model("core", "AuditLog")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    def user_by_id(raw):
        if not raw:
            return None
        try:
            return User.objects.filter(pk=raw).first()
        except (ValueError, TypeError):
            return None

    cancelled_orders = Order.objects.filter(status="cancelled", cancelled_at__isnull=True)
    for order in cancelled_orders.iterator(chunk_size=500):
        log = (
            AuditLog.objects.filter(entity="Order", object_id=str(order.pk), action="cancelled")
            .order_by("-created_at")
            .first()
        )
        meta = (log.metadata or {}) if log else {}
        order.cancelled_at = log.created_at if log else order.updated_at
        order.cancelled_by_id = getattr(log, "actor_id", None) if log else None
        authorizer = user_by_id(meta.get("authorized_by"))
        order.cancel_authorized_by = authorizer
        authorization = str(meta.get("authorization") or "")
        if authorization not in {"own", "delegated", "cash_password", "grace"}:
            authorization = ""
        order.cancel_authorization = authorization
        order.save(update_fields=["cancelled_at", "cancelled_by", "cancel_authorized_by", "cancel_authorization"])

    voided_items = OrderItem.objects.filter(status__in=["cancelled", "comped"], voided_at__isnull=True)
    for item in voided_items.iterator(chunk_size=500):
        log = (
            AuditLog.objects.filter(entity="OrderItem", object_id=str(item.pk), action="cancelled")
            .order_by("-created_at")
            .first()
        )
        item.voided_at = log.created_at if log else item.updated_at
        item.voided_by_id = getattr(log, "actor_id", None) if log else None
        item.save(update_fields=["voided_at", "voided_by"])


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0007_order_cancellation_details"),
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
