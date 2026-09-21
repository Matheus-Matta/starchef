import pytest
from rest_framework_simplejwt.tokens import AccessToken


@pytest.mark.django_db
def test_direct_table_order_is_rejected(api_client, manager_user, restaurant, table):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    response = api_client.post(
        "/api/v1/orders/",
        {
            "restaurant": str(restaurant.id),
            "order_type": "table",
            "table": str(table.id),
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "order_type" in str(response.data)


@pytest.mark.django_db
def test_comanda_vinculada_a_mesa_ocupa_a_mesa_sem_abrir_pedido(
    api_client, manager_user, table, command, product
):
    """A comanda NÃO abre pedido — ela anota, e a mesa fica ocupada por ela.

    Antes isto era `POST /orders/open-command/`, que criava um pedido para o
    cartão. Era esse gesto que prendia a comanda: desistir deixava um pedido
    vazio que alguém tinha de cancelar, e a mesa continuava ocupada por ele.
    """
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    vinculo = api_client.post(
        f"/api/v1/commands/{command.id}/link-table/",
        {"table_id": str(table.id)},
        format="json",
    )
    lancamento = api_client.post(
        f"/api/v1/commands/{command.id}/items/",
        {"product": str(product.id), "quantity": 2},
        format="json",
    )

    assert vinculo.status_code == 200, vinculo.data
    assert lancamento.status_code == 201, lancamento.data
    assert lancamento.data["command_status"] == "pending"
    # A ocupação do salão é decidida pelas comandas vinculadas.
    table.refresh_from_db()
    assert table.status == "occupied"

    from apps.orders.models import Order

    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_lancar_de_novo_no_mesmo_cartao_acrescenta(
    api_client, manager_user, command, product
):
    """Duas anotações no mesmo cartão, e nenhum pedido."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    primeira = api_client.post(
        f"/api/v1/commands/{command.id}/items/",
        {"product": str(product.id)},
        format="json",
    )
    segunda = api_client.post(
        f"/api/v1/commands/{command.id}/items/",
        {"product": str(product.id)},
        format="json",
    )

    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert primeira.data["id"] != segunda.data["id"]

    itens = api_client.get(f"/api/v1/commands/{command.id}/items/")
    assert len(itens.data["items"]) == 2
