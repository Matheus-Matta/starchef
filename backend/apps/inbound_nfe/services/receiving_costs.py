from decimal import Decimal

from django.db import models

from apps.inbound_nfe.models import InboundNFeItem
from apps.menu.models import Product
from apps.stock.models import StockMovement


def calculate_stock_unit_cost(item: InboundNFeItem, stock_quantity: Decimal) -> Decimal:
    """Calcula o custo unitario real, incluindo as despesas acessorias."""
    if stock_quantity <= 0:
        return Decimal("0")
    total = item.product_total - item.discount + item.freight + item.insurance + item.other_expenses
    return round(total / stock_quantity, 4)


def update_product_average_cost(product: Product, new_qty: Decimal, new_cost: Decimal):
    """Atualiza custos do produto sem alterar o preco de venda do gerente."""
    if not product or new_qty <= 0 or new_cost <= 0:
        return
    total_balance = (
        StockMovement.all_objects.filter(product=product)
        .aggregate(models.Sum("quantity"))["quantity__sum"] or Decimal("0")
    )
    previous_balance = max(Decimal("0"), total_balance - new_qty)
    current_avg = product.current_average_cost or Decimal("0")
    if previous_balance > 0 and current_avg > 0:
        total_qty = previous_balance + new_qty
        total_value = (previous_balance * current_avg) + (new_qty * new_cost)
        product.current_average_cost = round(total_value / total_qty, 4)
    else:
        product.current_average_cost = round(new_cost, 4)
    product.last_purchase_cost = round(new_cost, 4)
    product.estimated_cost = round(product.current_average_cost, 2)
    if product.sale_price and product.sale_price > 0:
        product.margin_percent = round(
            ((product.sale_price - product.estimated_cost) / product.sale_price) * 100, 2
        )
    else:
        product.margin_percent = Decimal("0.00")
    product.save(update_fields=[
        "current_average_cost", "last_purchase_cost", "estimated_cost", "margin_percent",
    ])
