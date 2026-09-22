"""Pagar esvazia a comanda. É o fim do ciclo do cartão.

O pedido do caixa puxa as anotações PENDENTES dos cartões; quando ele é pago,
elas saem da comanda como VENDA e o cartão volta para a gaveta. Sem isso o
cartão fica ocupado para sempre — e, pior, as mesmas anotações reaparecem no
próximo pagamento, prontas para serem cobradas de novo.

Havia dois caminhos para um pedido virar pago e só um concluía as anotações:
o fechamento com ajuste de taxa (`orders.services`) chamava
`conclude_items_of_order`; o REGISTRO DE PAGAMENTO (`payments.services`), que
é por onde o caixa passa de verdade, não chamava.
"""
import uuid
from decimal import Decimal

import pytest

from apps.orders.command_billing import attach_commands_to_order
from apps.orders.command_items import launch_item
from apps.orders.models import Order
from apps.orders.models_command_item import CommandItem
from apps.orders.services import create_order
from apps.restaurants.models import Command


pytestmark = pytest.mark.django_db


@pytest.fixture
def comanda(account, restaurant, branch):
    return Command.objects.create(
        account=account, restaurant=restaurant, branch=branch, number=901
    )


@pytest.fixture
def conta_com_comanda(
    contexto_tenant, restaurant, branch, manager_user, comanda, produto,
    sem_caixa_obrigatorio,
):
    """Uma comanda com consumo, puxada para um pedido do caixa."""
    launch_item(command=comanda, product=produto, user=manager_user, quantity=2)
    pedido = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COMMAND,
        user=manager_user,
    )
    attach_commands_to_order(order=pedido, command_ids=[comanda.pk], user=manager_user)
    pedido.refresh_from_db()
    return pedido


def _pagar_tudo(pedido, manager_user, metodo):
    from apps.payments.services import register_payment

    return register_payment(
        order=pedido,
        user=manager_user,
        payment_method_id=metodo.id,
        amount=Decimal(str(pedido.total)),
        idempotency_key=f"teste-{uuid.uuid4()}",
    )


def test_pagar_CONCLUI_as_anotacoes_da_comanda(
    conta_com_comanda, comanda, manager_user, dinheiro
):
    """O defeito. As anotações ficavam pendentes depois de pagas."""
    _pagar_tudo(conta_com_comanda, manager_user, dinheiro)

    pendentes = CommandItem.objects.filter(
        command=comanda, command_status=CommandItem.STATUS_PENDENTE
    )
    assert not pendentes.exists(), (
        "as anotações continuam pendentes depois do pagamento — a comanda "
        "seria cobrada de novo"
    )


def test_pagar_marca_como_VENDA_e_nao_como_perda(
    conta_com_comanda, comanda, manager_user, dinheiro
):
    """Venda e perda são estados diferentes, e o relatório depende disso."""
    _pagar_tudo(conta_com_comanda, manager_user, dinheiro)

    item = CommandItem.objects.filter(command=comanda).first()
    assert item.command_status == CommandItem.STATUS_COBRADO


def test_pagar_LIBERA_o_cartao_para_o_proximo_cliente(
    conta_com_comanda, comanda, manager_user, dinheiro
):
    """Cartão pago é cartão livre. É o que devolve a mesa ao salão."""
    _pagar_tudo(conta_com_comanda, manager_user, dinheiro)

    comanda.refresh_from_db()
    assert comanda.status == Command.STATUS_FREE
    assert comanda.current_order_id is None


def test_o_proximo_pagamento_NAO_ve_as_anotacoes_ja_cobradas(
    conta_com_comanda, comanda, manager_user, dinheiro
):
    """O sintoma que o operador vê: os itens reaparecendo no pagamento.

    `pending_items_of` é o que o caixa puxa. Depois de pago, ele precisa vir
    vazio — senão o cliente seguinte herda a conta do anterior.
    """
    from apps.orders.command_billing import pending_items_of

    _pagar_tudo(conta_com_comanda, manager_user, dinheiro)

    assert list(pending_items_of([comanda.pk])) == []


def test_pagar_TIRA_o_cartao_da_mesa(
    contexto_tenant, restaurant, branch, manager_user, produto, mesa, dinheiro,
    sem_caixa_obrigatorio, account,
):
    """Cartão livre não pode continuar sentado.

    O salão decide ocupação pelas comandas vinculadas. Um cartão pago que
    segue na mesa a mantém ocupada para o próximo cliente — e o operador,
    olhando o mapa, procura uma conta que já foi embora.
    """
    from apps.orders.command_items import launch_item

    comanda = Command.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        number=902, current_table=mesa,
    )
    launch_item(command=comanda, product=produto, user=manager_user, quantity=1)
    pedido = create_order(
        restaurant=restaurant, branch=branch,
        order_type=Order.TYPE_COMMAND, user=manager_user,
    )
    attach_commands_to_order(order=pedido, command_ids=[comanda.pk], user=manager_user)
    pedido.refresh_from_db()

    _pagar_tudo(pedido, manager_user, dinheiro)

    comanda.refresh_from_db()
    assert comanda.status == Command.STATUS_FREE
    assert comanda.current_table_id is None, (
        "o cartão foi pago e liberado, mas continua sentado na mesa"
    )
