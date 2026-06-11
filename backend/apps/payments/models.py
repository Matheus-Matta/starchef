from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TenantModel


class PaymentMethod(TenantModel):
    TYPE_CASH = "cash"
    TYPE_CARD = "card"
    TYPE_PIX = "pix"
    TYPE_VOUCHER = "voucher"
    TYPE_OTHER = "other"

    TYPE_CHOICES = [
        (TYPE_CASH, "Cash"),
        (TYPE_CARD, "Card"),
        (TYPE_PIX, "PIX"),
        (TYPE_VOUCHER, "Voucher"),
        (TYPE_OTHER, "Other"),
    ]

    name = models.CharField(max_length=80)
    method_type = models.CharField(max_length=24, choices=TYPE_CHOICES)
    requires_reference = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_payment_method_by_branch"),
        ]

    def __str__(self):
        return self.name


class Payment(TenantModel):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_CANCELLED = "cancelled"
    STATUS_REFUNDED = "refunded"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    order = models.ForeignKey("orders.Order", related_name="payments", on_delete=models.PROTECT)
    payment_method = models.ForeignKey(PaymentMethod, related_name="payments", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    change_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_APPROVED, db_index=True)
    idempotency_key = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="unique_payment_idempotency_by_account",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "paid_at"]),
            models.Index(fields=["order", "status"]),
        ]

    def __str__(self):
        return f"{self.order} - {self.amount}"


class CashRegister(TenantModel):
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
    ]

    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="cash_registers_opened",
        on_delete=models.PROTECT,
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="cash_registers_closed",
        on_delete=models.SET_NULL,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expected_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    difference_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["branch", "status", "opened_at"]),
        ]

    def __str__(self):
        return f"Cash register {self.opened_at:%Y-%m-%d} - {self.branch}"


class CashMovement(TenantModel):
    TYPE_OPENING = "opening"
    TYPE_SALE = "sale"
    TYPE_WITHDRAWAL = "withdrawal"
    TYPE_SUPPLY = "supply"
    TYPE_CLOSING = "closing"
    TYPE_ADJUSTMENT = "adjustment"

    TYPE_CHOICES = [
        (TYPE_OPENING, "Opening"),
        (TYPE_SALE, "Sale"),
        (TYPE_WITHDRAWAL, "Withdrawal"),
        (TYPE_SUPPLY, "Supply"),
        (TYPE_CLOSING, "Closing"),
        (TYPE_ADJUSTMENT, "Adjustment"),
    ]

    cash_register = models.ForeignKey(CashRegister, related_name="movements", on_delete=models.CASCADE)
    payment = models.ForeignKey(Payment, null=True, blank=True, related_name="cash_movements", on_delete=models.SET_NULL)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="cash_movements", on_delete=models.PROTECT)
    movement_type = models.CharField(max_length=24, choices=TYPE_CHOICES, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["cash_register", "movement_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.movement_type} - {self.amount}"
