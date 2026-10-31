import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.orders.models import Order
from apps.orders.services import create_order
from apps.restaurants.models import Command, Table, TableSector


pytestmark = pytest.mark.django_db


def test_transferencia_de_comandas_grava_cada_colecao_uma_unica_vez(
    admin_client, account, restaurant, branch, manager_user
):
    """Duas comandas não podem virar duas atualizações de comandas e pedidos."""
    setor = TableSector.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Salão",
    )
    origem = Table.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        sector=setor,
        number="1",
        capacity=4,
    )
    destino = Table.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        sector=setor,
        number="2",
        capacity=4,
    )
    comandas = [
        Command.objects.create(
            account=account,
            restaurant=restaurant,
            branch=branch,
            current_table=origem,
        )
        for _ in range(2)
    ]
    pedidos = [
        create_order(
            restaurant=restaurant,
            branch=branch,
            order_type=Order.TYPE_COUNTER,
            user=manager_user,
        )
        for _ in comandas
    ]
    for comanda, pedido in zip(comandas, pedidos, strict=True):
        comanda.current_order_id = pedido.id
        comanda.save(update_fields=["current_order_id", "updated_at"])

    with CaptureQueriesContext(connection) as queries:
        response = admin_client.post(
            f"/api/v1/tables/{origem.id}/transfer-commands/",
            {"to_table_id": str(destino.id)},
            format="json",
        )

    assert response.status_code == 200, response.content
    sql = [query["sql"] for query in queries.captured_queries]
    updates_de_comanda = [query for query in sql if 'UPDATE "restaurants_command"' in query]
    updates_de_pedido = [query for query in sql if 'UPDATE "orders_order"' in query]
    assert len(updates_de_comanda) == 1
    assert len(updates_de_pedido) == 1

    assert Command.all_objects.filter(
        pk__in=[item.pk for item in comandas], current_table=destino
    ).count() == 2
    assert Order.all_objects.filter(pk__in=[item.pk for item in pedidos], table=destino).count() == 2
