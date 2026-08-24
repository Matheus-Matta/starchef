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
