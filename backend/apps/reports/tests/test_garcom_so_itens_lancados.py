"""O relatório do garçom conta só o que foi LANÇADO.

Item que nunca saiu para a produção nem veio de uma anotação de comanda (o
lançamento do garçom) não é venda dele: ficava somando como se fosse.
Cancelado e cortesia já não entravam.
"""
from decimal import Decimal

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.orders.models import CommandItem, Order, OrderItem
from apps.reports.tests.test_waiter_sales_report import product  # noqa: F401 — fixture
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


def _pedido_pago(account, restaurant, branch, user, sequencia):
    return Order.objects.create(
        account=account, restaurant=restaurant, branch=branch, sequence=sequencia,
        order_type=Order.TYPE_COUNTER, status=Order.STATUS_PAID,
        payment_status=Order.PAYMENT_PAID, responsible_user=user, total="25.00",
    )


def _item(pedido, produto, status, **extra):  # noqa: F811
    return OrderItem.objects.create(
        account=pedido.account, restaurant=pedido.restaurant, branch=pedido.branch, order=pedido,
        product=produto, quantity="1.000", unit_price="25.00", total_price="25.00",
        status=status, launched_by=pedido.responsible_user, **extra,
    )


def test_so_itens_lancados_entram_no_relatorio_do_garcom(
    api_client, account, restaurant, branch, manager_user, product,  # noqa: F811
):
    pedido = _pedido_pago(account, restaurant, branch, manager_user, 900)
    _item(pedido, product, OrderItem.STATUS_DELIVERED)  # saiu para a produção: conta
    _item(pedido, product, OrderItem.STATUS_PENDING)  # nunca lançado: não conta
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch)
    anotacao = CommandItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, command=comanda, product=product,
        quantity="1.000", unit_price="25.00", total_price="25.00", launched_by=manager_user,
    )
    # veio da anotação do garçom: conta, mesmo sem setor de produção
    _item(pedido, product, OrderItem.STATUS_PENDING, command=comanda, command_item=anotacao)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    [linha] = api_client.get("/api/v1/reports/waiters/").data["by_waiter"]

    assert linha["items"] == 2
    assert linha["total"] == Decimal("50.00")
