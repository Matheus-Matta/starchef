from django.db import models

from apps.core.models import TenantModel


class CommandItemAddon(TenantModel):
    """Adicional escolhido enquanto o consumo ainda está na comanda."""

    item = models.ForeignKey(
        "orders.CommandItem",
        related_name="addons",
        on_delete=models.CASCADE,
    )
    addon = models.ForeignKey(
        "menu.ProductAddon",
        related_name="command_item_addons",
        on_delete=models.PROTECT,
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.addon} ({self.item})"
