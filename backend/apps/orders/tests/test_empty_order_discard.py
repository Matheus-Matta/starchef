"""Descartar um pedido VAZIO nao e cancelar uma venda.

Abrir uma comanda cria o pedido na hora — e ele que ocupa a comanda. Se o
operador sai sem lancar item nenhum, esse pedido vazio fica segurando a
comanda e o proximo cliente que pegar a mesma nao consegue usa-la. Nao ha
consumo a estornar nem motivo a registrar, entao nao ha o que autorizar.
"""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order, order_is_empty

pytestmark = pytest.mark.django_db


@pytest.fixture
def empty_order(restaurant, branch, manager_user):
    return create_order(
        restaurant=restaurant, branch=branch,
        order_type=Order.TYPE_COUNTER, user=manager_user,
    )


@pytest.fixture
def product(account, restaurant, branch):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Coxinha", internal_code=f"P{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("6.00"),
    )


def test_pedido_sem_item_e_vazio(account, empty_order):
    with tenant_context(account):
        assert order_is_empty(empty_order) is True


def test_pedido_com_item_nao_e_vazio(account, empty_order, product, manager_user):
    add_order_item(order=empty_order, product=product, quantity=1, user=manager_user)

    with tenant_context(account):
        assert order_is_empty(empty_order) is False


def test_descarte_do_vazio_dispensa_autorizacao(empty_order, api_client):
    # Sem senha de operacao e sem credencial de supervisor no corpo.
    response = api_client.post(
        f"/api/v1/orders/{empty_order.id}/cancel/", {}, format="json"
    )

    assert response.status_code == 200, response.data
    empty_order.refresh_from_db()
    assert empty_order.status == Order.STATUS_CANCELLED


def test_pedido_com_consumo_continua_exigindo_autorizacao(
    empty_order, product, manager_user, api_client
):
    add_order_item(order=empty_order, product=product, quantity=1, user=manager_user)

    response = api_client.post(
        f"/api/v1/orders/{empty_order.id}/cancel/",
        {"reason": "cliente desistiu"},
        format="json",
    )

    # A protecao existe para impedir que alguem apague consumo ja lancado.
    assert response.status_code == 403
    empty_order.refresh_from_db()
    assert empty_order.status != Order.STATUS_CANCELLED
