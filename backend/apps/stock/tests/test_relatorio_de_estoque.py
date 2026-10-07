"""Relatório de estoque: filtros por fornecedor e categoria, código e CSV.

O insumo não tem categoria própria: a categoria é a dos produtos que o
consomem (venda direta da prateleira ou ficha técnica).
"""
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product, ProductCategory, Recipe, RecipeItem
from apps.stock.models import Supplier
from apps.stock.tests.test_stock_positions import (  # noqa: F401 — fixtures
    _ingredient,
    _movement,
    _positions,
    _tenant,
    account_with_logistica,
    location,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario(account_with_logistica, restaurant, branch, manager_user, location):  # noqa: F811
    conta = account_with_logistica
    with tenant_context(conta):
        ambev = Supplier.objects.create(account=conta, name="Ambev")
        moinho = Supplier.objects.create(account=conta, name="Moinho")
        bebidas = ProductCategory.objects.create(account=conta, restaurant=restaurant, name="Bebidas")
        lanches = ProductCategory.objects.create(account=conta, restaurant=restaurant, name="Lanches")
        lata = _ingredient(conta, restaurant, branch, manager_user, "Coca lata", unit="un",
                           supplier=ambev, average_cost=Decimal("3.1234"))
        farinha = _ingredient(conta, restaurant, branch, manager_user, "Farinha", supplier=moinho)
        Product.objects.create(account=conta, restaurant=restaurant, category=bebidas, name="Coca-Cola",
                               internal_code="BEB-01", sale_price=Decimal("6"), stock_ingredient=lata)
        pao = Product.objects.create(account=conta, restaurant=restaurant, category=lanches, name="Pão",
                                     internal_code="LAN-01", sale_price=Decimal("2"))
        receita = Recipe.objects.create(account=conta, restaurant=restaurant, product=pao)
        RecipeItem.objects.create(account=conta, restaurant=restaurant, recipe=receita,
                                  ingredient=farinha, quantity=Decimal("0.1"), unit="kg")
        _movement(conta, restaurant, branch, manager_user, location, lata, "10")
    return {"ambev": ambev, "bebidas": bebidas, "lanches": lanches}


def test_filtra_por_fornecedor(api_client, cenario):
    linhas = _positions(api_client.get("/api/v1/stock/positions/", {"supplier": cenario["ambev"].pk}))
    assert set(linhas) == {"Coca lata"}
    assert linhas["Coca lata"]["supplier_name"] == "Ambev"


def test_filtra_pela_categoria_dos_produtos_que_consomem(api_client, cenario):
    bebidas = _positions(api_client.get("/api/v1/stock/positions/", {"category": cenario["bebidas"].pk}))
    lanches = _positions(api_client.get("/api/v1/stock/positions/", {"category": cenario["lanches"].pk}))
    assert set(bebidas) == {"Coca lata"}
    assert set(lanches) == {"Farinha"}


def test_codigo_vem_do_produto_vendido_direto(api_client, cenario):
    linhas = _positions(api_client.get("/api/v1/stock/positions/"))
    assert linhas["Coca lata"]["code"] == "BEB-01"


def test_exporta_csv_com_valores_em_2_casas(api_client, cenario):
    resposta = api_client.get("/api/v1/stock/positions/", {"export": "csv"})

    assert resposta.status_code == 200
    texto = resposta.content.decode("utf-8")
    assert "Coca lata" in texto
    assert "3.12" in texto and "31.23" in texto
    assert "3.1234" not in texto
