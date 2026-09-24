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
    # Regras declarativas avaliadas na leitura do quadro. A migration deixa
    # estações já existentes com [] e o serializer fornece a regra padrão
    # somente para estações criadas depois desta funcionalidade.
    rules = models.JSONField(default=list, blank=True)
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
    # Item parado NESTA coluna não pode ser cancelado.
    #
    # É a regra do cozinheiro: depois que o prato entrou na chapa, tirá-lo da
    # conta não desfaz o insumo nem o tempo. Marcar "Em preparo" e "Pronto"
    # cobre o caso comum; a coluna de entrada normalmente fica livre.
    #
    # Nasce DESLIGADA, e em coluna nova também: uma coluna criada no meio do
    # almoço não pode começar bloqueando algo que ninguém configurou.
    blocks_cancel = models.BooleanField(
        default=False,
        help_text="Item nesta coluna não pode ser cancelado (exige autorização).",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["station", "position", "id"]
        indexes = [models.Index(fields=["station", "position"])]

    def __str__(self):
        return f"{self.station.name} · {self.name}"


class KdsItemPosition(TenantBaseModel):
    """Posição independente de um item em cada estação KDS."""

    station = models.ForeignKey(KdsStation, related_name="item_positions", on_delete=models.CASCADE)
    item = models.ForeignKey("orders.OrderItem", related_name="kds_positions", on_delete=models.CASCADE)
    column = models.ForeignKey(KdsColumn, related_name="item_positions", on_delete=models.CASCADE)
    entered_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["station", "item"], name="unique_kds_position_per_station_item"),
        ]
        indexes = [models.Index(fields=["station", "column"])]

    def __str__(self):
        return f"{self.station.name} · {self.item_id} · {self.column.name}"
