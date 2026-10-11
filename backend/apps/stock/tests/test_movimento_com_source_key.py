"""O movimento de estoque com `source_key` tem o MESMO id na loja e na nuvem.

Achado no par Docker (`loadtest/dia_a_dia`): com o item de pedido de UUID
calculado (pedido + anotação), a mesma venda que chegou aos dois servidores
fez a MESMA baixa nos dois — mesma `source_key` (`sale:<item>:recipe_item:<x>`).
Cada um sorteava o id do movimento, e na chegada a trava única da
`source_key` virava conflito (95 num teste de 8 minutos). Calculado da
`source_key`, é o mesmo movimento, e a sincronização junta.
"""
import uuid
from decimal import Decimal

import pytest

from apps.menu.models import Recipe, RecipeItem
from apps.stock.models import StockMovement
from apps.stock.movement_ids import id_do_movimento
from apps.stock.services import deduct_order_stock
from apps.stock.tests.test_stock_engine import (  # noqa: F401 — fixtures
    _ingredient, _order_with_item, _tenant, category, product,
)

pytestmark = pytest.mark.django_db


def test_baixa_da_venda_tem_id_calculado_da_source_key(
    account, restaurant, branch, manager_user, product  # noqa: F811
):
    carne = _ingredient(account, restaurant, branch, manager_user, name="Carne", unit="g")
    receita = Recipe.objects.create(account=account, restaurant=restaurant, branch=branch,
                                    product=product, yield_quantity=Decimal("1"),
                                    created_by=manager_user, updated_by=manager_user)
    RecipeItem.objects.create(account=account, restaurant=restaurant, branch=branch, recipe=receita,
                              ingredient=carne, quantity=Decimal("150"), unit="g",
                              created_by=manager_user, updated_by=manager_user)
    pedido, _ = _order_with_item(account, restaurant, branch, manager_user, product)

    [movimento] = deduct_order_stock(order=pedido, user=manager_user)

    assert movimento.source_key
    assert movimento.pk == id_do_movimento(account.pk, movimento.source_key)


def test_sem_source_key_o_id_continua_sorteado():
    assert isinstance(StockMovement().pk, uuid.UUID)
