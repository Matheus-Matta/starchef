"""O saldo de estoque do produto como SUBCONSULTA da lista.

A lista de produtos somava os movimentos de cada produto em duas consultas
(`current_stock` e `current_stock_display`). Anotado, sai na mesma consulta da
página — a mesma soma (movimentos não apagados), zero quando não há nenhum.
"""
from decimal import Decimal

from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce


def estoque_do_produto():
    from apps.stock.models import StockMovement

    soma = (
        StockMovement.all_objects.filter(product=OuterRef("pk"), deleted_at__isnull=True)
        .order_by()
        .values("product")
        .annotate(total=Sum("quantity"))
        .values("total")
    )
    campo = DecimalField(max_digits=18, decimal_places=4)
    return Coalesce(Subquery(soma, output_field=campo), Value(Decimal("0"), output_field=campo))
