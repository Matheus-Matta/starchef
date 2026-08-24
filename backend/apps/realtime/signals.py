from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from apps.core.models import TenantBaseModel

from .events import broadcast_model_event


def _publish(instance, action, *, update_fields=None):
    account_id = getattr(instance, "account_id", None)
    if not account_id:
        return
    payload = {
        "resource": instance._meta.label_lower,
        "model": instance._meta.model_name,
        "action": action,
        "id": str(instance.pk),
        "branch_id": str(getattr(instance, "branch_id", "") or ""),
        "restaurant_id": str(getattr(instance, "restaurant_id", "") or ""),
        "changed_fields": sorted(update_fields or []),
        "occurred_at": str(getattr(instance, "updated_at", "") or ""),
        "protocol_version": 1,
    }
    transaction.on_commit(
        lambda: broadcast_model_event(account_id, f"model.{action}", payload)
    )


@receiver(post_save)
def tenant_model_saved(sender, instance, created, raw=False, update_fields=None, **kwargs):
    if raw or not isinstance(instance, TenantBaseModel):
        return
    # Audit entries are implementation detail and extremely noisy.
    if instance._meta.label_lower == "core.auditlog":
        return
    deleted = bool(getattr(instance, "deleted_at", None))
    action = "created" if created else "deleted" if deleted else "updated"
    _publish(instance, action, update_fields=update_fields)


@receiver(post_delete)
def tenant_model_deleted(sender, instance, **kwargs):
    if isinstance(instance, TenantBaseModel):
        _publish(instance, "deleted")


@receiver(m2m_changed)
def tenant_relation_changed(sender, instance, action, **kwargs):
    if not isinstance(instance, TenantBaseModel) or not action.startswith("post_"):
        return
    _publish(instance, "updated", update_fields={"relations"})
