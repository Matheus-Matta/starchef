"""A comanda só fica livre quando a conta dela está PAGA — e volta a ficar
presa quando o pagamento é desfeito.

Os dois furos que a análise da loja provou:

* **Total R$ 0,00** (desconto de 100%): o PDV concluía sem recebimento, o
  servidor respondia 201, mas o pedido ficava "aguardando pagamento" para
  sempre e a comanda continuava ocupada — presa a uma venda que acabou.
* **Pagamento excluído** de uma comanda já paga: o pedido voltava a "não
  pago", mas as anotações seguiam "cobradas" e a comanda aparecia LIVRE — a
  balança automática podia entregá-la ao próximo cliente, e quem tentasse
  cobrá-la caía na conta do cliente anterior.
"""
import uuid

import pytest

from apps.core.tenant import tenant_context
from apps.orders.command_item_launch import launch_item
from apps.orders.models import CommandItem, Order
from apps.orders.tests.test_venda_inteira import URL, _venda
from apps.payments.models import Payment
from apps.payments.services import cancel_payment
from apps.restaurants.command_listing import anotar_estado
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


@pytest.fixture
def comanda(account, restaurant, branch):
    return Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=77)


def _livre_para_a_balanca(comanda):
    with tenant_context(comanda.account):
        return anotar_estado(Command.objects.filter(pk=comanda.pk)).filter(
            pendentes=0, pedido_aberto=False).exists()


def test_venda_de_total_zero_quita_o_pedido_e_libera_a_comanda(
    api_client, contexto_tenant, sem_caixa_obrigatorio, comanda, restaurant, produto, manager_user
):
    item = launch_item(command=comanda, product=produto, user=manager_user)
    corpo = {**_venda(restaurant, produto, comandas=[comanda], itens=0), "payments": [],
             "close": {"discount": "25.00", "service_fee_enabled": False}}

    resposta = api_client.post(URL, corpo, format="json")

    assert resposta.status_code == 201, resposta.content
    pedido = Order.all_objects.get(pk=corpo["id"])
    assert pedido.total == 0
    assert pedido.payment_status == Order.PAYMENT_PAID
    item.refresh_from_db()
    assert item.command_status == CommandItem.STATUS_COBRADO
    comanda.refresh_from_db()
    assert comanda.status == Command.STATUS_FREE


def test_desconto_parcial_sem_pagamento_continua_esperando_o_pagamento(
    api_client, contexto_tenant, sem_caixa_obrigatorio, comanda, restaurant, produto, manager_user
):
    """O total zero quita; total que ainda deve, não — nada de quitar por engano."""
    launch_item(command=comanda, product=produto, user=manager_user)
    corpo = {**_venda(restaurant, produto, comandas=[comanda], itens=0), "payments": [],
             "close": {"discount": "5.00", "service_fee_enabled": False}}

    api_client.post(URL, corpo, format="json")

    pedido = Order.all_objects.get(pk=corpo["id"])
    assert pedido.payment_status != Order.PAYMENT_PAID
    comanda.refresh_from_db()
    assert comanda.status == Command.STATUS_OCCUPIED


def test_excluir_o_pagamento_devolve_a_comanda_para_em_uso(
    api_client, contexto_tenant, sem_caixa_obrigatorio, comanda, restaurant, produto, dinheiro,
    manager_user
):
    item = launch_item(command=comanda, product=produto, user=manager_user)
    corpo = _venda(restaurant, produto, dinheiro, valor="25.00", comandas=[comanda], itens=0)
    assert api_client.post(URL, corpo, format="json").status_code == 201
    comanda.refresh_from_db()
    assert comanda.status == Command.STATUS_FREE

    cancel_payment(payment=Payment.all_objects.get(order_id=corpo["id"]), user=manager_user)

    item.refresh_from_db()
    assert item.command_status == CommandItem.STATUS_PENDENTE
    comanda = Command.all_objects.get(pk=comanda.pk)
    assert comanda.status == Command.STATUS_OCCUPIED
    assert not _livre_para_a_balanca(comanda)


def test_depois_do_estorno_a_mesma_conta_e_paga_de_novo_e_libera(
    api_client, contexto_tenant, sem_caixa_obrigatorio, comanda, restaurant, produto, dinheiro,
    manager_user
):
    """O cliente pagou em dinheiro, o caixa estornou para trocar por cartão."""
    launch_item(command=comanda, product=produto, user=manager_user)
    corpo = _venda(restaurant, produto, dinheiro, valor="25.00", comandas=[comanda], itens=0)
    api_client.post(URL, corpo, format="json")
    cancel_payment(payment=Payment.all_objects.get(order_id=corpo["id"]), user=manager_user)

    de_novo = {**corpo, "payments": [{**corpo["payments"][0], "id": str(uuid.uuid4())}]}
    resposta = api_client.post(URL, de_novo, format="json")

    assert resposta.status_code in (200, 201), resposta.content
    assert Order.all_objects.get(pk=corpo["id"]).payment_status == Order.PAYMENT_PAID
    comanda = Command.all_objects.get(pk=comanda.pk)
    assert comanda.status == Command.STATUS_FREE
