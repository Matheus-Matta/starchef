"""A lista de produtos em consultas FIXAS, não por produto.

Cada produto custava 4 consultas a mais (duas somas de estoque, a receita e os
adicionais): 1.200 consultas para um cardápio de 300 itens. No pdv.log de um
caixa que "travava", uma página de produtos levava 13 s e o PDV a relia o
tempo todo — o servidor da loja inteiro engasgava.
"""
import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.menu.models import Ingredient, Product, ProductAddon, ProductCategory, Recipe, RecipeItem
from apps.stock.models import StockLocation, StockMovement

pytestmark = pytest.mark.django_db
URL = "/api/v1/menu/products/"


def _cardapio(account, restaurant, branch, n):
    categoria = ProductCategory.objects.create(account=account, restaurant=restaurant, branch=branch,
                                               name=f"C{uuid.uuid4().hex[:4]}")
    adicional = ProductAddon.objects.create(account=account, restaurant=restaurant, branch=branch,
                                            name=f"Bacon {uuid.uuid4().hex[:4]}", price=Decimal("3.00"))
    ingrediente = Ingredient.objects.create(account=account, restaurant=restaurant, branch=branch,
                                            name=f"Pão {uuid.uuid4().hex[:4]}", unit="UN")
    produtos = []
    for i in range(n):
        produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch,
                                         category=categoria, name=f"Prato {i}",
                                         internal_code=f"I{uuid.uuid4().hex[:6]}", sale_price=Decimal("10"))
        produto.addons.add(adicional)
        receita = Recipe.objects.create(account=account, restaurant=restaurant, branch=branch, product=produto)
        RecipeItem.objects.create(account=account, restaurant=restaurant, branch=branch, recipe=receita,
                                  ingredient=ingrediente, quantity=Decimal("1"))
        produtos.append(produto)
    return produtos


def _consultas(api_client, restaurant):
    with CaptureQueriesContext(connection) as ctx:
        resposta = api_client.get(URL, {"page_size": 60, "restaurant": str(restaurant.pk), "is_active": True})
    assert resposta.status_code == 200, resposta.content
    return len(ctx.captured_queries), resposta.json()["results"]


def test_mais_produtos_nao_custam_mais_consultas(api_client, account, restaurant, branch):
    _cardapio(account, restaurant, branch, 3)
    poucos, _ = _consultas(api_client, restaurant)
    _cardapio(account, restaurant, branch, 20)
    muitos, _ = _consultas(api_client, restaurant)

    assert muitos == poucos


def test_o_que_a_lista_mostra_continua_igual(api_client, account, restaurant, branch, manager_user):
    (produto,) = _cardapio(account, restaurant, branch, 1)
    produto.stock_unit = "UN"
    produto.save(update_fields=["stock_unit"])
    local = StockLocation.objects.create(account=account, restaurant=restaurant, branch=branch, name="Depósito")
    for quantidade in ("5", "-2"):
        StockMovement.objects.create(account=account, restaurant=restaurant, branch=branch, product=produto,
                                     quantity=Decimal(quantidade), movement_type=StockMovement.TYPE_IN,
                                     operator=manager_user, location=local)

    _, (linha,) = _consultas(api_client, restaurant)

    assert linha["current_stock"] == 3.0
    assert linha["current_stock_display"] == "3 UN"
    assert linha["addons"][0]["name"].startswith("Bacon")
    assert linha["recipe"]["items"][0]["ingredient_name"].startswith("Pão")
