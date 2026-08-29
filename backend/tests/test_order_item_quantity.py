"""Quantidade de um item pelo teclado do PDV (`+` e `-`).

A regra que carrega o peso: só item PENDENTE muda. Um item já despachado
descreve o que a cozinha recebeu — alterar a quantidade dele reescreveria o
passado sem ninguém na produção ficar sabendo. Para esse caso existem o
cancelamento e a cortesia, que avisam o setor.
"""
from decimal import Decimal

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.orders.models import Order, OrderItem
from apps.orders.services import add_order_item, create_order, send_order_to_kitchen

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def authenticated(api_client, manager_user):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}"
    )
    return api_client


@pytest.fixture
def order_with_item(restaurant, branch, table, product, manager_user):
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_TABLE,
        table=table,
        user=manager_user,
    )
    item = add_order_item(order=order, product=product, quantity=2, user=manager_user)
    return order, item


def change(client, order, item, quantity):
    return client.post(
        f"/api/v1/orders/{order.id}/items/{item.id}/quantity/",
        {"quantity": quantity},
        format="json",
    )


def test_quantity_and_line_total_follow_each_other(api_client, order_with_item):
    order, item = order_with_item

    response = change(api_client, order, item, 5)

    assert response.status_code == 200, response.data
    item.refresh_from_db()
    assert item.quantity == Decimal("5")
    assert item.total_price == item.unit_price * 5


def test_the_order_total_is_recalculated(api_client, order_with_item):
    order, item = order_with_item

    change(api_client, order, item, 5)

    order.refresh_from_db()
    assert order.subtotal == item.unit_price * 5


def test_a_dispatched_item_is_refused(api_client, order_with_item, manager_user):
    order, item = order_with_item
    send_order_to_kitchen(order=order, user=manager_user)

    response = change(api_client, order, item, 5)

    assert response.status_code == 400, response.data
    item.refresh_from_db()
    assert item.quantity == Decimal("2")


def test_zero_is_refused_because_removing_needs_a_reason(api_client, order_with_item):
    order, item = order_with_item

    response = change(api_client, order, item, 0)

    assert response.status_code == 400, response.data
    item.refresh_from_db()
    assert item.status == OrderItem.STATUS_PENDING
    assert item.quantity == Decimal("2")


def test_garbage_does_not_become_a_server_error(api_client, order_with_item):
    order, item = order_with_item

    response = change(api_client, order, item, "muitos")

    assert response.status_code == 400, response.data


def test_an_unknown_item_is_not_found(api_client, order_with_item):
    order, _ = order_with_item

    response = api_client.post(
        f"/api/v1/orders/{order.id}/items/00000000-0000-4000-8000-000000000000/quantity/",
        {"quantity": 3},
        format="json",
    )

    assert response.status_code == 404, response.data


def test_a_weighed_product_keeps_the_scale_as_the_source(
    api_client, restaurant, branch, table, product, manager_user
):
    product.pricing_unit = product.PRICING_KG
    product.save(update_fields=["pricing_unit"])
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_TABLE,
        table=table,
        user=manager_user,
    )
    item = add_order_item(
        order=order, product=product, weight_kg="0.412", user=manager_user
    )

    response = change(api_client, order, item, 2)

    assert response.status_code == 400, response.data
    item.refresh_from_db()
    assert item.quantity == Decimal("0.412")
