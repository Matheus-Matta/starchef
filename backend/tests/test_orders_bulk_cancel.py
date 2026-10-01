"""Cancelar vários pedidos de uma vez, com a regra do cancelamento de um."""
import pytest

from apps.core.tenant import tenant_context
from apps.orders.models import Order
from apps.orders.services import add_order_item, cancel_order, create_order, send_order_to_kitchen

pytestmark = pytest.mark.django_db
URL = "/api/v1/orders/bulk-cancel/"


def _autenticar(api_client):
    api_client.force_authenticate(user=None)
    login = api_client.post(
        "/api/v1/auth/login/",
        {"username": "manager", "password": "secret123", "no_cookie": True},
        format="json",
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")


def _pedidos(restaurant, branch, table, product, user):
    with tenant_context(restaurant.account):
        pedidos = []
        for _ in range(2):
            pedido = create_order(restaurant=restaurant, branch=branch, order_type="counter", user=user)
            add_order_item(order=pedido, product=product, quantity=1, user=user)
            send_order_to_kitchen(pedido, user)
            pedidos.append(pedido)
        cancelado = create_order(restaurant=restaurant, branch=branch, order_type="counter", user=user)
        add_order_item(order=cancelado, product=product, quantity=1, user=user)
        cancel_order(cancelado, user, "antes", authorization=Order.AUTHORIZATION_CASH_PASSWORD)
    return pedidos, cancelado


def test_sem_senha_nenhum_pedido_com_consumo_e_cancelado(api_client, manager_user, restaurant, branch, table, product):
    """A massa não pode ser o atalho que dispensa a senha de cancelamento."""
    _autenticar(api_client)
    restaurant.set_cash_action_password("caixa123")
    restaurant.save(update_fields=["cash_action_password"])
    pedidos, _ = _pedidos(restaurant, branch, table, product, manager_user)

    resposta = api_client.post(URL, {"ids": [str(p.id) for p in pedidos], "reason": "Teste"}, format="json")

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["cancelled"] == 0
    assert {s["reason"] for s in resposta.json()["skipped"]} == {"precisa da senha de operação"}
    assert not Order.all_objects.filter(pk__in=[p.pk for p in pedidos], status=Order.STATUS_CANCELLED).exists()


def test_com_a_senha_cancela_todos_e_pula_o_ja_cancelado(api_client, manager_user, restaurant, branch, table, product):
    _autenticar(api_client)
    restaurant.set_cash_action_password("caixa123")
    restaurant.save(update_fields=["cash_action_password"])
    pedidos, cancelado = _pedidos(restaurant, branch, table, product, manager_user)
    ids = [str(p.id) for p in pedidos] + [str(cancelado.id)]

    resposta = api_client.post(
        URL, {"ids": ids, "reason": "Fechamento do teste", "cash_password": "caixa123"}, format="json"
    )

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["cancelled"] == 2
    assert [s["reason"] for s in resposta.json()["skipped"]] == ["já estava cancelado"]
    for pedido in pedidos:
        pedido.refresh_from_db()
        assert pedido.status == Order.STATUS_CANCELLED
        assert pedido.cancel_authorization == Order.AUTHORIZATION_CASH_PASSWORD


def test_motivo_e_obrigatorio(api_client, manager_user, restaurant, branch, table, product):
    _autenticar(api_client)
    pedidos, _ = _pedidos(restaurant, branch, table, product, manager_user)

    resposta = api_client.post(URL, {"ids": [str(pedidos[0].id)]}, format="json")

    assert resposta.status_code == 400
