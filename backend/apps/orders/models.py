from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Order(TenantModel):
    TYPE_TABLE = "table"
    TYPE_COMMAND = "command"
    TYPE_COUNTER = "counter"
    TYPE_DELIVERY = "delivery"
    TYPE_TAKEAWAY = "takeaway"
    TYPE_INTERNAL = "internal"

    TYPE_CHOICES = [
        (TYPE_TABLE, "Table"),
        (TYPE_COMMAND, "Command"),
        (TYPE_COUNTER, "Counter"),
        (TYPE_DELIVERY, "Delivery"),
        (TYPE_TAKEAWAY, "Takeaway"),
        (TYPE_INTERNAL, "Internal"),
    ]

    # Operational cycle (conta aberta)
    STATUS_OPEN = "open"
    STATUS_AWAITING_PAYMENT = "awaiting_payment"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"
    STATUS_REFUNDED = "refunded"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_AWAITING_PAYMENT, "Awaiting payment"),
        (STATUS_PAID, "Paid"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    # Production cycle (cozinha) — independent of status
    PROD_IDLE = "idle"
    PROD_SENT = "sent_to_kitchen"
    PROD_PREPARING = "preparing"
    PROD_PARTIALLY_READY = "partially_ready"
    PROD_READY = "ready"
    PROD_DELIVERED = "delivered"

    PRODUCTION_STATUS_CHOICES = [
        (PROD_IDLE, "Idle"),
        (PROD_SENT, "Sent to kitchen"),
        (PROD_PREPARING, "Preparing"),
        (PROD_PARTIALLY_READY, "Partially ready"),
        (PROD_READY, "Ready"),
        (PROD_DELIVERED, "Delivered"),
    ]

    # Payment cycle — independent of status and production_status
    PAYMENT_PENDING = "pending"
    PAYMENT_PARTIAL = "partial"
    PAYMENT_PAID = "paid"
    PAYMENT_REFUNDED = "refunded"

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_PARTIAL, "Partial"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_REFUNDED, "Refunded"),
    ]

    # Delivery cycle — só relevante para pedidos de entrega (módulo Entrega).
    DELIVERY_PENDING = "pending"
    DELIVERY_OUT = "out_for_delivery"
    DELIVERY_DELIVERED = "delivered"
    DELIVERY_FAILED = "failed"

    DELIVERY_STATUS_CHOICES = [
        (DELIVERY_PENDING, "Pending"),
        (DELIVERY_OUT, "Out for delivery"),
        (DELIVERY_DELIVERED, "Delivered"),
        (DELIVERY_FAILED, "Failed"),
    ]

    sequence = models.PositiveIntegerField()
    order_type = models.CharField(max_length=24, choices=TYPE_CHOICES)
    table = models.ForeignKey(
        "restaurants.Table",
        null=True,
        blank=True,
        related_name="orders",
        on_delete=models.SET_NULL,
    )
    command = models.ForeignKey(
        "restaurants.Command",
        null=True,
        blank=True,
        related_name="orders",
        on_delete=models.SET_NULL,
    )
    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        related_name="orders",
        on_delete=models.SET_NULL,
    )
    delivery_address = models.ForeignKey(
        "customers.CustomerAddress",
        null=True,
        blank=True,
        related_name="delivery_orders",
        on_delete=models.SET_NULL,
    )
    responsible_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="orders_opened",
        on_delete=models.SET_NULL,
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="orders_closed",
        on_delete=models.SET_NULL,
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    production_status = models.CharField(
        max_length=32,
        choices=PRODUCTION_STATUS_CHOICES,
        default=PROD_IDLE,
        db_index=True,
    )
    opened_at = models.DateTimeField(auto_now_add=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_PENDING,
        db_index=True,
    )
    delivery_status = models.CharField(
        max_length=24,
        choices=DELIVERY_STATUS_CHOICES,
        default=DELIVERY_PENDING,
        db_index=True,
    )
    general_notes = models.TextField(blank=True)
    change_history = models.JSONField(default=list, blank=True)
    cancel_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "sequence"], name="unique_order_sequence_by_branch"),
        ]
        indexes = [
            models.Index(fields=["branch", "status", "opened_at"]),
            models.Index(fields=["branch", "payment_status"]),
            models.Index(fields=["restaurant", "opened_at"]),
        ]

    def __str__(self):
        return f"Order {self.sequence}"

    @property
    def is_locked(self):
        return self.status in {self.STATUS_PAID, self.STATUS_CANCELLED, self.STATUS_REFUNDED}


class OrderBatch(TenantModel):
    """Production round — group of items sent to kitchen at once within a single order."""

    STATUS_SENT = "sent"
    STATUS_DONE = "done"

    STATUS_CHOICES = [
        (STATUS_SENT, "Sent"),
        (STATUS_DONE, "Done"),
    ]

    order = models.ForeignKey(Order, related_name="batches", on_delete=models.CASCADE)
    batch_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SENT)
    sent_at = models.DateTimeField()
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="batches_sent",
        on_delete=models.SET_NULL,
    )
    printed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["batch_number"]
        constraints = [
            models.UniqueConstraint(fields=["order", "batch_number"], name="unique_batch_number_per_order"),
        ]

    def __str__(self):
        return f"Rodada #{self.batch_number} — Pedido {self.order_id}"


class OrderItem(TenantModel):
    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_PREPARING = "preparing"
    STATUS_READY = "ready"
    STATUS_DELIVERED = "delivered"
    STATUS_CANCELLED = "cancelled"
    STATUS_COMPED = "comped"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_PREPARING, "Preparing"),
        (STATUS_READY, "Ready"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_COMPED, "Comped"),
    ]

    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    batch = models.ForeignKey(
        OrderBatch,
        null=True,
        blank=True,
        related_name="items",
        on_delete=models.SET_NULL,
    )
    product = models.ForeignKey("menu.Product", related_name="order_items", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    variations = models.JSONField(default=list, blank=True)
    customer_note = models.TextField(blank=True)
    production_sector = models.CharField(max_length=20, db_index=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    # Coluna atual no quadro do KDS (Kanban). Nulo = ainda não posicionado
    # (o card aparece na coluna de entrada da estação). Ref. por string p/ evitar
    # ciclo de import entre orders <-> kitchen.
    kds_column = models.ForeignKey(
        "kitchen.KdsColumn",
        null=True,
        blank=True,
        related_name="order_items",
        on_delete=models.SET_NULL,
    )
    launched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="order_items_launched",
        on_delete=models.SET_NULL,
    )
    launched_at = models.DateTimeField(auto_now_add=True)
    sent_to_kitchen_at = models.DateTimeField(null=True, blank=True)
    preparation_started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["launched_at"]
        indexes = [
            models.Index(fields=["branch", "production_sector", "status"]),
            models.Index(fields=["order", "status"]),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.product}"


class OrderItemAddon(TenantModel):
    item = models.ForeignKey(OrderItem, related_name="addons", on_delete=models.CASCADE)
    addon = models.ForeignKey("menu.ProductAddon", related_name="order_item_addons", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.addon} ({self.item})"
