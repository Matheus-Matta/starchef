from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class StockLocation(TenantModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_stock_location_by_branch"),
        ]

    def __str__(self):
        return self.name


class StockMovement(TenantModel):
    TYPE_IN = "in"
    TYPE_OUT = "out"
    TYPE_ADJUSTMENT = "adjustment"
    TYPE_SALE = "sale"
    TYPE_INVENTORY = "inventory"

    TYPE_CHOICES = [
        (TYPE_IN, "In"),
        (TYPE_OUT, "Out"),
        (TYPE_ADJUSTMENT, "Adjustment"),
        (TYPE_SALE, "Sale"),
        (TYPE_INVENTORY, "Inventory"),
    ]

    ingredient = models.ForeignKey("menu.Ingredient", related_name="stock_movements", on_delete=models.PROTECT)
    location = models.ForeignKey(StockLocation, related_name="movements", on_delete=models.PROTECT)
    order_item = models.ForeignKey("orders.OrderItem", null=True, blank=True, related_name="stock_movements", on_delete=models.SET_NULL)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="stock_movements", on_delete=models.PROTECT)
    movement_type = models.CharField(max_length=24, choices=TYPE_CHOICES, db_index=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reason = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["branch", "ingredient", "created_at"]),
            models.Index(fields=["branch", "movement_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.ingredient} {self.quantity}"

