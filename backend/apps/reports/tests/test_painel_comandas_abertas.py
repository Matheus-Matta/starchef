"""A visão geral diz quanto dinheiro está em comandas abertas.

A tabela de pedidos recentes mostrava conta por conta, e o gerente somava de
cabeça. O total segue a MESMA regra da lista de comandas do PDV
(`command_listing.anotar_estado`): anotação pendente, sem cancelada nem
cortesia — senão o painel e o caixa discordariam do mesmo cartão.
"""
from decimal import Decimal

import pytest

from apps.orders.command_item_launch import launch_item
from apps.orders.command_item_void import void_command_item
from apps.orders.tests.conftest import categoria, contexto_tenant, produto  # noqa: F401
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


def _comanda(account, restaurant, branch, numero):
    return Command.objects.create(account=account, restaurant=restaurant, branch=branch,
                                  number=numero)


def test_soma_o_pendente_das_comandas_e_conta_os_cartoes(
    api_client, contexto_tenant, account, restaurant, branch, produto, manager_user  # noqa: F811
):
    c15 = _comanda(account, restaurant, branch, 15)
    c16 = _comanda(account, restaurant, branch, 16)
    _comanda(account, restaurant, branch, 17)  # vazia: não conta
    launch_item(command=c15, product=produto, user=manager_user)
    launch_item(command=c15, product=produto, user=manager_user)
    launch_item(command=c16, product=produto, user=manager_user)
    cancelado = launch_item(command=c16, product=produto, user=manager_user)
    void_command_item(cancelado, user=manager_user, reason="errado", authorized=True)

    dados = api_client.get("/api/v1/reports/dashboard/").json()

    assert Decimal(str(dados["open_commands_total"])) == Decimal("75.00")
    assert dados["open_commands_count"] == 2
