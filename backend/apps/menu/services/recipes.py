from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.core.numbers import fits_decimal


@transaction.atomic
def recalculate_recipe_costs(recipe):
    """Recalculate RecipeItem costs from Ingredient.average_cost, then propagate to Recipe and Product."""
    # Um recalculo por ficha de cada vez. Dois itens lancados ao mesmo tempo na
    # mesma ficha (dois terminais, ou o painel com clique duplo) recalculavam
    # em paralelo e atualizavam as mesmas linhas em ordens diferentes —
    # `deadlock detected` no Postgres, 500 para o usuario. A trava e na linha
    # da receita, e `_base_manager` porque o manager padrao filtra por conta e
    # este servico tambem roda fora de request (Celery, manage.py).
    recipe = type(recipe)._base_manager.select_for_update().get(pk=recipe.pk)
    total = Decimal("0.00")
    for item in recipe.items.select_related("ingredient").order_by("pk"):
        cost = item.ingredient.average_cost
        item.ingredient_cost = cost
        # Quantidade e custo cabem cada um na sua coluna, mas o PRODUTO dos dois
        # pode não caber em `total_cost` (12 dígitos). Django converte o Decimal
        # com precisão igual a `max_digits` no momento de gravar, e um valor
        # maior levantava `InvalidOperation` lá dentro — 500 sem nenhuma pista
        # de qual insumo causou. Perguntar aqui deixa o erro nomear o culpado.
        computed = (Decimal(str(item.quantity)) * cost).quantize(Decimal("0.01"))
        if not fits_decimal(computed, max_digits=12, decimal_places=2):
            raise ValidationError(
                f"O custo de '{item.ingredient}' fica grande demais nesta ficha "
                f"({item.quantity} x {cost}). Revise a quantidade ou o custo médio do insumo."
            )
        item.total_cost = computed
        item.save(update_fields=["ingredient_cost", "total_cost", "updated_at"])
        total += item.total_cost

    if not fits_decimal(total, max_digits=12, decimal_places=2):
        raise ValidationError(
            "O custo total desta ficha técnica ultrapassa o limite. Revise as quantidades."
        )
    recipe.total_cost = total
    recipe.save(update_fields=["total_cost", "updated_at"])

    product = recipe.product
    # Rendimento minúsculo (0,001) transforma um custo normal num número que
    # não cabe em `estimated_cost`: a divisão multiplica por mil. O guard do
    # total acima não pega este caso, porque o estouro nasce aqui.
    yield_qty = recipe.yield_quantity or Decimal("1")
    if yield_qty <= 0:
        raise ValidationError("O rendimento da ficha técnica precisa ser maior que zero.")
    estimated = (total / Decimal(str(yield_qty))).quantize(Decimal("0.01"))
    if not fits_decimal(estimated, max_digits=12, decimal_places=2):
        raise ValidationError(
            "O custo por unidade fica grande demais com este rendimento. "
            "Revise o rendimento ou as quantidades da ficha."
        )
    product.estimated_cost = estimated
    if product.sale_price and product.sale_price > 0:
        margem = (
            (product.sale_price - product.estimated_cost) / product.sale_price * 100
        ).quantize(Decimal("0.01"))
        # `margin_percent` tem só 6 dígitos: um custo muito acima do preço
        # produz percentual de milhares e estoura a coluna na gravação.
        product.margin_percent = (
            margem if fits_decimal(margem, max_digits=6, decimal_places=2) else Decimal("-9999.99")
        )
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
