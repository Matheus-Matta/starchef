"""Erros de criação de pedido viram 400 claro (não 500)."""

import pytest

from apps.restaurants.models import Table, TableSector

pytestmark = pytest.mark.django_db


def test_direct_table_order_returns_400(api_client, account, restaurant, branch):
    sector = TableSector.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Salão",
    )
    table = Table.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        sector=sector,
        number="10",
        capacity=4,
    )
    response = api_client.post(
        "/api/v1/orders/",
        {"order_type": "table", "table": str(table.id)},
        format="json",
    )

    assert response.status_code == 400, response.data


def test_patch_discount_recalculates_the_total(api_client, account, restaurant, branch):
    """`discount` é gravável pela API genérica — o total tem que acompanhar.

    Sem o gancho de recálculo o desconto entrava e o `total` continuava o
    antigo: a mesma divergência que derrubava o fechamento do PDV, por outra
    porta.
    """
    import uuid
    from decimal import Decimal

    from apps.menu.models import Product
    from apps.orders.models import Order
    from apps.orders.services import add_order_item, create_order

    product = Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Produto desconto",
        internal_code=f"DESC-{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("30.00"),
    )
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=None,
    )
    add_order_item(order=order, product=product, quantity=1, user=None)

    response = api_client.patch(
        f"/api/v1/orders/{order.pk}/",
        {"discount": "5.00"},
        format="json",
    )

    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.discount == Decimal("5.00")
    assert order.total == Decimal("25.00")
