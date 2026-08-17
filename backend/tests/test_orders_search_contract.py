"""Contrato de busca/filtro/ordenacao da lista de pedidos.

O PDV Desktop passou a mandar `search`, `ordering`, `order_type`, `payment_status`
e o intervalo de datas para a API em vez de filtrar so o que ja baixou. Estes
testes travam esse contrato: se um parametro deixar de existir ou de aceitar o
formato enviado, a tela de Pedidos para de achar pedido antigo sem que ninguem
perceba.
"""
import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.restaurants.models import Command


@pytest.fixture
def authed(api_client, manager_user):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")
    return api_client


def _results(response):
    return response.data["results"] if "results" in response.data else response.data


@pytest.mark.django_db
def test_text_search_does_not_break_on_numeric_columns(authed, manager_user, restaurant, branch):
    """Termo nao numerico com `sequence` na busca.

    `sequence` e inteiro; a busca do DRF usa `icontains`. Sem o cast para texto
    isso quebra em PostgreSQL ("operator does not exist: integer ~~* unknown"),
    e o SQLite dos testes nao denunciaria sozinho.
    """
    create_order(
        restaurant=restaurant, branch=branch,
        order_type=Order.TYPE_COUNTER, user=manager_user,
    )

    response = authed.get("/api/v1/orders/", {"search": "maria"})

    assert response.status_code == 200, response.data
    assert _results(response) == []


@pytest.mark.django_db
def test_search_finds_order_by_sequence_and_command(authed, manager_user, account, restaurant, branch):
    command = Command.objects.create(
        account=account, restaurant=restaurant, branch=branch, number=77,
    )
    order = create_order(
        restaurant=restaurant, branch=branch,
        order_type=Order.TYPE_COMMAND, command=command, user=manager_user,
    )

    by_sequence = authed.get("/api/v1/orders/", {"search": str(order.sequence)})
    by_command_code = authed.get("/api/v1/orders/", {"search": command.code})
    by_command_number = authed.get("/api/v1/orders/", {"search": "77"})

    assert [item["id"] for item in _results(by_sequence)] == [str(order.id)]
    assert [item["id"] for item in _results(by_command_code)] == [str(order.id)]
    assert [item["id"] for item in _results(by_command_number)] == [str(order.id)]


@pytest.mark.django_db
def test_ordering_and_filters_accepted(authed, manager_user, restaurant, branch, product):
    cheap = create_order(
        restaurant=restaurant, branch=branch,
        order_type=Order.TYPE_COUNTER, user=manager_user,
    )
    add_order_item(order=cheap, product=product, quantity=1, user=manager_user)
    pricey = create_order(
        restaurant=restaurant, branch=branch,
        order_type=Order.TYPE_TAKEAWAY, user=manager_user,
    )
    add_order_item(order=pricey, product=product, quantity=5, user=manager_user)

    by_total = authed.get("/api/v1/orders/", {"ordering": "-total"})
    by_type = authed.get("/api/v1/orders/", {"order_type": Order.TYPE_TAKEAWAY})
    by_range = authed.get(
        "/api/v1/orders/",
        {"opened_after": "2000-01-01", "opened_before": "2100-01-01"},
    )
    cheap.payment_status = Order.PAYMENT_PARTIAL
    cheap.save(update_fields=["payment_status"])
    by_payment = authed.get("/api/v1/orders/", {"payment_pending": "true"})

    assert [item["id"] for item in _results(by_total)][0] == str(pricey.id)
    assert [item["id"] for item in _results(by_type)] == [str(pricey.id)]
    assert len(_results(by_range)) == 2
    # O agrupamento da tela inclui tanto pendente quanto pagamento parcial.
    assert len(_results(by_payment)) == 2


@pytest.mark.django_db
def test_default_ordering_uses_latest_update(authed, manager_user, restaurant, branch):
    older = create_order(
        restaurant=restaurant, branch=branch,
        order_type=Order.TYPE_COUNTER, user=manager_user,
    )
    newer = create_order(
        restaurant=restaurant, branch=branch,
        order_type=Order.TYPE_TAKEAWAY, user=manager_user,
    )
    older.general_notes = "Pedido atualizado por ultimo"
    older.save(update_fields=["general_notes"])

    response = authed.get("/api/v1/orders/")

    assert [item["id"] for item in _results(response)][:2] == [str(older.id), str(newer.id)]
