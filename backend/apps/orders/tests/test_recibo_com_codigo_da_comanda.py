"""O recibo da venda por comanda sai com o código de barras no final.

Desde que a comanda virou bloco de notas, o pedido nasce NO CAIXA a partir das
anotações dos cartões, e `order.command` fica vazio. O código de barras era
tirado só de `order.command` — e sumiu do recibo, justamente o que permite
reler a comanda depois sem digitar nada.
"""
import pytest

from apps.orders.command_billing import attach_commands_to_order
from apps.orders.command_items import launch_item
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.printers.services import _customer_receipt_text, _order_command_barcode
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


def _conta(restaurant, branch, user, produto, *comandas):
    for comanda in comandas:
        launch_item(command=comanda, product=produto, user=user, quantity=1)
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND, user=user)
    attach_commands_to_order(order=pedido, command_ids=[c.pk for c in comandas], user=user)
    return Order.all_objects.get(pk=pedido.pk)


def test_conta_de_uma_comanda_imprime_o_codigo_dela(
    contexto_tenant, account, restaurant, branch, manager_user, produto, sem_caixa_obrigatorio
):
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=41)
    pedido = _conta(restaurant, branch, manager_user, produto, comanda)

    assert pedido.command_id is None  # o pedido nasce no caixa, sem cabeçalho de comanda
    assert _order_command_barcode(pedido)["value"] == (comanda.code or str(comanda.number))
    assert "COMANDA - CODE128" in _customer_receipt_text(pedido)


def test_conta_agrupada_lista_todas_e_imprime_o_codigo_da_primeira(
    contexto_tenant, account, restaurant, branch, manager_user, produto, sem_caixa_obrigatorio
):
    base = {"account": account, "restaurant": restaurant, "branch": branch}
    c12 = Command.objects.create(number=12, **base)
    c7 = Command.objects.create(number=7, **base)
    pedido = _conta(restaurant, branch, manager_user, produto, c12, c7)

    assert _order_command_barcode(pedido)["value"] == (c7.code or "7")
    assert "COMANDAS 7, 12" in _customer_receipt_text(pedido)
