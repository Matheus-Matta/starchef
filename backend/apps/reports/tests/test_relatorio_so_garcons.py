"""O relatório de garçom lista só quem tem o perfil Garçom.

Caixa e gerente também lançam item (no balcão, no PDV) e apareciam no
relatório como se fossem garçons. O autor do item é quem ANOTOU na comanda,
quando houve anotação — o caixa que transformou a comanda em pedido não é o
garçom daquele prato.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import UserProfile
from apps.accounts.role_catalog import ensure_system_roles
from apps.orders.models import CommandItem, Order, OrderItem
from apps.reports.tests.test_waiter_sales_report import product  # noqa: F401 — fixture
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


def _usuario(account, restaurant, branch, nome, perfil):
    user = User.objects.create_user(username=nome, password="x")
    UserProfile.objects.create(account=account, user=user, role=ensure_system_roles(account)[perfil],
                               restaurant=restaurant, branch=branch)
    return user


def test_so_garcons_e_o_autor_e_quem_anotou(api_client, account, restaurant, branch, manager_user, product):  # noqa: F811
    joao = _usuario(account, restaurant, branch, "joao", "waiter")
    caixa = _usuario(account, restaurant, branch, "caixa1", "cashier")
    pedido = Order.objects.create(account=account, restaurant=restaurant, branch=branch, sequence=7,
                                  order_type=Order.TYPE_COMMAND, status=Order.STATUS_PAID,
                                  payment_status=Order.PAYMENT_PAID, total="75.00")
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch)

    def item(lancou, anotou=None):
        anotacao = None
        if anotou:
            anotacao = CommandItem.objects.create(
                account=account, restaurant=restaurant, branch=branch, command=comanda, product=product,
                quantity="1.000", unit_price="25.00", total_price="25.00", launched_by=anotou)
        OrderItem.objects.create(account=account, restaurant=restaurant, branch=branch, order=pedido,
                                 product=product, quantity="1.000", unit_price="25.00", total_price="25.00",
                                 status=OrderItem.STATUS_DELIVERED, launched_by=lancou, command_item=anotacao,
                                 command=comanda if anotou else None)

    item(lancou=caixa, anotou=joao)  # o caixa cobrou, mas quem anotou foi o João: conta para ele
    item(lancou=caixa)  # venda do caixa no balcão: fora
    item(lancou=manager_user)  # gerente: fora
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    linhas = api_client.get("/api/v1/reports/waiters/").data["by_waiter"]

    assert [(linha["operator_username"], linha["items"]) for linha in linhas] == [("joao", 1)]
