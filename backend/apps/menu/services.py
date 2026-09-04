from decimal import Decimal

from django.db import transaction
from django.db.models import Sum


@transaction.atomic
def recalculate_recipe_costs(recipe):
    """Recalculate RecipeItem costs from Ingredient.average_cost, then propagate to Recipe and Product."""
    total = Decimal("0.00")
    for item in recipe.items.select_related("ingredient").all():
        cost = item.ingredient.average_cost
        item.ingredient_cost = cost
        item.total_cost = (Decimal(str(item.quantity)) * cost).quantize(Decimal("0.01"))
        item.save(update_fields=["ingredient_cost", "total_cost", "updated_at"])
        total += item.total_cost

    recipe.total_cost = total
    recipe.save(update_fields=["total_cost", "updated_at"])

    product = recipe.product
    yield_qty = recipe.yield_quantity or Decimal("1")
    product.estimated_cost = (total / Decimal(str(yield_qty))).quantize(Decimal("0.01"))
    if product.sale_price and product.sale_price > 0:
        product.margin_percent = (
            (product.sale_price - product.estimated_cost) / product.sale_price * 100
        ).quantize(Decimal("0.01"))
    else:
        product.margin_percent = Decimal("0.00")
    product.save(update_fields=["estimated_cost", "margin_percent", "updated_at"])
    return recipe


@transaction.atomic
def update_ingredient_average_cost(ingredient, incoming_quantity, incoming_unit_cost):
    """Update Ingredient.average_cost using weighted average when stock comes in.

    A entrada e chamada DEPOIS que o movimento foi gravado, entao o saldo lido
    aqui ja inclui a quantidade que esta chegando. Some-la de novo contaria a
    entrada duas vezes e puxaria a media na direcao do custo novo — o preco de
    uma compra grande virava praticamente o custo medio do insumo. Descontar a
    entrada devolve o saldo ANTERIOR, que e a base correta da ponderacao.
    """
    from apps.stock.models import StockMovement

    incoming_quantity = Decimal(str(incoming_quantity))
    incoming_unit_cost = Decimal(str(incoming_unit_cost))

    # `all_objects` com o filtro de conta explicito, e nao o manager com escopo
    # de tenant: este servico e chamado de dentro de outros servicos, onde o
    # contexto ambiente pode nao estar definido. Sem conta no contexto, o
    # manager devolve queryset vazio — o saldo viria zero e a media passaria a
    # ser simplesmente o custo da ultima compra, sem ponderacao nenhuma.
    balance = (
        StockMovement.all_objects.filter(
            account_id=ingredient.account_id,
            ingredient=ingredient,
            branch=ingredient.branch,
            deleted_at__isnull=True,
        ).aggregate(balance=Sum("quantity"))["balance"]
        or Decimal("0")
    )
    current_stock = balance - incoming_quantity
    current_cost = ingredient.average_cost

    if current_stock > Decimal("0") and incoming_quantity > Decimal("0"):
        new_avg = (current_stock * current_cost + incoming_quantity * incoming_unit_cost) / (
            current_stock + incoming_quantity
        )
    elif incoming_quantity > Decimal("0"):
        new_avg = incoming_unit_cost
    else:
        return ingredient

    ingredient.average_cost = new_avg.quantize(Decimal("0.0001"))
    ingredient.save(update_fields=["average_cost", "updated_at"])

    for recipe_item in ingredient.recipe_items.select_related("recipe__product").all():
        recalculate_recipe_costs(recipe_item.recipe)

    return ingredient
