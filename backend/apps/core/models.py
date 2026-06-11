import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.tenant import get_current_account


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(UUIDModel):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditUserModel(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
        on_delete=models.SET_NULL,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
        on_delete=models.SET_NULL,
    )

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        return super().update(is_deleted=True, deleted_at=timezone.now())

    def active(self):
        return self.filter(is_deleted=False)


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)


class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    class Meta:
        abstract = True


class TenantQuerySet(models.QuerySet):
    def for_account(self, account):
        return self.filter(account=account)

    def active(self):
        filters = {"deleted_at__isnull": True}
        if hasattr(self.model, "is_active"):
            filters["is_active"] = True
        return self.filter(**filters)


class TenantManager(models.Manager):
    def get_queryset(self):
        account = get_current_account()
        queryset = TenantQuerySet(self.model, using=self._db)

        if account is None:
            return queryset.none()

        queryset = queryset.filter(account=account)
        if hasattr(self.model, "deleted_at"):
            queryset = queryset.filter(deleted_at__isnull=True)
        return queryset


class TenantBaseModel(TimeStampedModel, AuditUserModel):
    account = models.ForeignKey(
        "accounts.Account",
        related_name="%(class)s_set",
        on_delete=models.PROTECT,
        db_index=True,
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["account"]),
            models.Index(fields=["account", "created_at"]),
            models.Index(fields=["account", "deleted_at"]),
        ]

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])


class TenantModel(TenantBaseModel):
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        related_name="%(class)s_set",
        on_delete=models.PROTECT,
    )
    branch = models.ForeignKey(
        "restaurants.Branch",
        related_name="%(class)s_set",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["account", "restaurant"]),
            models.Index(fields=["account", "branch"]),
            models.Index(fields=["account", "created_at"]),
        ]


class AuditLog(TenantBaseModel):
    ACTION_CREATED = "created"
    ACTION_UPDATED = "updated"
    ACTION_DELETED = "deleted"
    ACTION_CANCELLED = "cancelled"
    ACTION_PAYMENT = "payment"
    ACTION_PRINTED = "printed"

    ACTION_CHOICES = [
        (ACTION_CREATED, "Created"),
        (ACTION_UPDATED, "Updated"),
        (ACTION_DELETED, "Deleted"),
        (ACTION_CANCELLED, "Cancelled"),
        (ACTION_PAYMENT, "Payment"),
        (ACTION_PRINTED, "Printed"),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        related_name="audit_logs",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    branch = models.ForeignKey(
        "restaurants.Branch",
        related_name="audit_logs",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    action = models.CharField(max_length=32, choices=ACTION_CHOICES, db_index=True)
    entity = models.CharField(max_length=120, db_index=True)
    object_id = models.CharField(max_length=64, db_index=True)
    reason = models.TextField(blank=True)
    changes = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["account", "created_at"]),
            models.Index(fields=["restaurant", "branch", "created_at"]),
            models.Index(fields=["entity", "object_id"]),
        ]

    def __str__(self):
        return f"{self.action} {self.entity} {self.object_id}"
