"""Custo × venda por produto.

O custo vem da BAIXA DE ESTOQUE da venda: ela grava o custo da época, e o
estorno o devolve. Produto sem baixa (sem ficha nem vínculo de estoque) usa o
custo do cadastro — custo médio, ou o estimado da ficha — e a linha diz isso.
"""
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Ingredient, Product, ProductCategory
from apps.orders.models import Order, OrderItem
from apps.stock.models import StockLocation, StockMovement

pytestmark = pytest.mark.django_db
ROTA = "/api/v1/reports/product-costs/"


@pytest.fixture
def vendas(account, restaurant, branch, manager_user):
    with tenant_context(account):
        cat = ProductCategory.objects.create(account=account, restaurant=restaurant, name="Lanches")
        burger = Product.objects.create(account=account, restaurant=restaurant, category=cat, name="X-Burger",
                                        internal_code="XB", sale_price=Decimal("25"))
        suco = Product.objects.create(account=account, restaurant=restaurant, category=cat, name="Suco",
                                      internal_code="SU", sale_price=Decimal("8"), estimated_cost=Decimal("2.50"))
        carne = Ingredient.objects.create(account=account, restaurant=restaurant, name="Carne", unit="kg")
        local = StockLocation.objects.create(account=account, restaurant=restaurant, name="Cozinha")

        def pedido(seq, status=Order.STATUS_PAID):
            pago = status == Order.STATUS_PAID
            return Order.objects.create(account=account, restaurant=restaurant, sequence=seq, status=status,
                                        payment_status=Order.PAYMENT_PAID if pago else Order.PAYMENT_CANCELLED)

        def item(order, produto, qtd, total, status=OrderItem.STATUS_DELIVERED):
            return OrderItem.objects.create(account=account, restaurant=restaurant, order=order, product=produto,
                                            quantity=Decimal(qtd), unit_price=Decimal(total) / Decimal(qtd),
                                            total_price=Decimal(total), status=status)

        p1 = pedido(1)
        i1 = item(p1, burger, "2", "50.00")
        # A baixa da venda gravou o custo da época (negativo, como no livro).
        StockMovement.objects.create(account=account, restaurant=restaurant, location=local, ingredient=carne,
                                     order_item=i1, operator=manager_user, movement_type=StockMovement.TYPE_SALE_OUTPUT,
                                     quantity=Decimal("-0.4"), unit_cost=Decimal("40"), total_cost=Decimal("-16.00"))
        item(p1, suco, "3", "24.00")
        item(p1, burger, "1", "25.00", status=OrderItem.STATUS_CANCELLED)  # cancelado: fora
        item(pedido(2, Order.STATUS_CANCELLED), burger, "5", "125.00")  # pedido cancelado: fora


def test_custo_da_baixa_e_custo_do_cadastro_com_margem(vendas, admin_client):
    resposta = admin_client.get(ROTA)

    assert resposta.status_code == 200, resposta.data
    linhas = {linha["product_name"]: linha for linha in resposta.data["by_product"]}
    burger, suco = linhas["X-Burger"], linhas["Suco"]
    assert Decimal(burger["quantity"]) == Decimal("2")
    assert Decimal(burger["revenue"]) == Decimal("50.00")
    assert Decimal(burger["cost"]) == Decimal("16.00")
    assert Decimal(burger["margin"]) == Decimal("34.00")
    assert burger["cost_source"] == "baixa"
    assert Decimal(suco["cost"]) == Decimal("7.50")
    assert suco["cost_source"] == "cadastro"
    assert Decimal(resposta.data["totals"]["margin"]) == Decimal("50.50")


def test_exporta_csv(vendas, admin_client):
    texto = admin_client.get(ROTA, {"export": "csv"}).content.decode("utf-8")
    assert "X-Burger" in texto and "34.00" in texto
