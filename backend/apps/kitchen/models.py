from django.db import models

from apps.core.models import TenantBaseModel
from apps.restaurants.models import Branch, Restaurant


class KdsStation(TenantBaseModel):
    """Um "quadro" (board) de KDS. As colunas do quadro são criadas aqui
    (ver KdsColumn); os itens de pedido em produção viram cards que transitam
    entre as colunas por drag-and-drop."""

    name = models.CharField(max_length=100)
    restaurant = models.ForeignKey(Restaurant, related_name="kds_stations", on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, null=True, blank=True, related_name="kds_stations", on_delete=models.SET_NULL)
    sla_minutes = models.PositiveIntegerField(default=15)
    sectors = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class KdsColumn(TenantBaseModel):
    """Coluna (raia) livre de um quadro de KDS.

    O operador cria as colunas que quiser por estação. Uma coluna pode ser
    marcada como `is_entry` (onde os cards novos aparecem) e/ou `is_done`
    (coluna final: mover um card para cá conclui o item — marca como pronto).
    """

    station = models.ForeignKey(KdsStation, related_name="columns", on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    position = models.PositiveIntegerField(default=0, db_index=True)
    color = models.CharField(max_length=20, default="#64748b", help_text="Cor da coluna (hex).")
    is_entry = models.BooleanField(default=False, help_text="Cards novos aparecem nesta coluna.")
    is_done = models.BooleanField(default=False, help_text="Coluna final: concluir o item ao mover para cá.")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["station", "position", "id"]
        indexes = [models.Index(fields=["station", "position"])]

    def __str__(self):
        return f"{self.station.name} · {self.name}"
