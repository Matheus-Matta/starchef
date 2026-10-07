"""A lista de pedidos mostra a comanda mesmo quando ela veio pelos ITENS.

Desde que a comanda virou bloco de notas, o pedido nasce no caixa e as
comandas entram pelas anotações (`attach-commands`): `order.command` fica
vazio e a coluna "Comanda" da lista aparecia "-". O número está nos itens.
"""
import pytest

from apps.core.tenant import tenant_context
from apps.orders.models import Order, OrderItem
from apps.orders.services import add_order_item, create_order
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


def _pedido_do_caixa_com_comandas(account, restaurant, branch, user, produtos, numeros):
    with tenant_context(account):
        pedido = create_order(
            restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND, user=user,
        )
        for numero, produto in zip(numeros, produtos, strict=False):
            comanda = Command.objects.create(
                account=account, restaurant=restaurant, branch=branch, number=numero,
            )
            item = add_order_item(order=pedido, product=produto, quantity=1, user=user)
            OrderItem.objects.filter(pk=item.pk).update(command=comanda)
    return pedido


def test_comandas_dos_itens_aparecem_na_lista(
    account, restaurant, branch, manager_user, produto, produto_barato, api_client
):
    pedido = _pedido_do_caixa_com_comandas(
        account, restaurant, branch, manager_user, [produto, produto_barato], [107, 17]
    )

    resposta = api_client.get("/api/v1/orders/")

    assert resposta.status_code == 200, resposta.data
    linha = next(r for r in resposta.data["results"] if r["id"] == str(pedido.pk))
    assert linha["command"] is None
    assert linha["command_label"] == "17, 107"


def test_pedido_aberto_pela_comanda_continua_mostrando_ela(
    account, restaurant, branch, manager_user, api_client
):
    with tenant_context(account):
        comanda = Command.objects.create(
            account=account, restaurant=restaurant, branch=branch, number=5,
        )
        pedido = create_order(
            restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND,
            command=comanda, user=manager_user,
        )

    linha = api_client.get(f"/api/v1/orders/{pedido.pk}/").data

    assert linha["command_label"] == "5"


def test_balcao_sem_comanda_fica_vazio(account, restaurant, branch, manager_user, api_client):
    with tenant_context(account):
        pedido = create_order(
            restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user,
        )

    assert api_client.get(f"/api/v1/orders/{pedido.pk}/").data["command_label"] == ""
