"""A listagem de pedidos precisa bastar para editar um pedido offline.

O PDV desktop guarda a página de pedidos no cache local. Se a listagem
deixasse de trazer os itens, o operador voltaria a não conseguir abrir um
pedido feito em outro caixa quando a rede caísse — e a falha só apareceria no
balcão, não aqui. Por isso o contrato está fixado em um teste.
"""

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order


@pytest.fixture
def authenticated(api_client, manager_user):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}"
    )
    return api_client


@pytest.mark.django_db
def test_listagem_traz_os_itens_de_cada_pedido(
    authenticated,
    restaurant,
    branch,
    table,
    product,
    manager_user,
):
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_TABLE,
        table=table,
        user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=2, user=manager_user)

    response = authenticated.get("/api/v1/orders/", {"page_size": 50})

    assert response.status_code == 200, response.content
    listed = response.data["results"][0]
    # É isto que permite abrir o pedido sem rede: a lista já é o detalhe.
    assert "items" in listed
    assert len(listed["items"]) == 1
    item = listed["items"][0]
    assert item["product_name"] == product.name
    assert item["quantity"] is not None
    assert item["total_price"] is not None
    # Campos que o carrinho do PDV usa para desenhar a linha.
    for field in ("status", "unit_price", "pricing_unit"):
        assert field in item


@pytest.mark.django_db
def test_a_pagina_respeita_o_tamanho_pedido(
    authenticated,
    restaurant,
    branch,
    product,
    manager_user,
):
    for _ in range(4):
        order = create_order(
            restaurant=restaurant,
            branch=branch,
            order_type=Order.TYPE_COUNTER,
            user=manager_user,
        )
        add_order_item(order=order, product=product, quantity=1, user=manager_user)

    response = authenticated.get("/api/v1/orders/", {"page_size": 2})

    assert response.status_code == 200
    assert len(response.data["results"]) == 2
    assert response.data["count"] == 4
    # O cliente guarda uma página; ela precisa vir completa mesmo limitada.
    assert response.data["results"][0]["items"]
