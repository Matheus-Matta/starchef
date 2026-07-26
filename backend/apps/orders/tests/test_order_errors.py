"""Erros de criação de pedido viram 400 claro (não 500)."""
import pytest

from apps.restaurants.models import Table, TableSector

pytestmark = pytest.mark.django_db


def test_order_on_occupied_table_returns_400(api_client, account, restaurant, branch):
    sector = TableSector.objects.create(account=account, restaurant=restaurant, branch=branch, name="Salão")
    table = Table.objects.create(
        account=account, restaurant=restaurant, branch=branch, sector=sector, number="10", capacity=4
    )
    r1 = api_client.post("/api/v1/orders/", {"order_type": "table", "table": str(table.id)}, format="json")
    assert r1.status_code == 201, r1.data

    # Mesa já ocupada: antes dava 500 (django ValidationError não tratado), agora 400.
    r2 = api_client.post("/api/v1/orders/", {"order_type": "table", "table": str(table.id)}, format="json")
    assert r2.status_code == 400, r2.data
