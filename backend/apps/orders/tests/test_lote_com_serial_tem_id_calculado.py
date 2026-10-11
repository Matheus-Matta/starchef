"""O lote da cozinha com o serial do PDV tem o MESMO id na loja e na nuvem.

Achado no par Docker (`loadtest/dia_a_dia`): a venda inteira com "mandar à
cozinha" chegou aos DOIS servidores — a loja gravou e caiu antes de responder,
o terminal reenviou à nuvem. Pedido, itens e recebimentos se juntaram pelo UUID;
o lote, não: cada servidor sorteou o id dele com o MESMO serial, e a
sincronização batia na trava única do serial — o lote nunca entrava, e os itens
que apontam para ele ficavam retentando para sempre.
"""
import uuid

import pytest

from apps.orders.command_item_launch import launch_item
from apps.orders.command_kitchen import send_command_to_kitchen
from apps.orders.models import Order
from apps.orders.production_ids import id_do_lote
from apps.orders.services import add_order_item, create_order, send_order_to_kitchen
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


def test_lote_do_pedido_com_serial_tem_id_calculado(contexto_tenant, restaurant, branch, produto,
                                                    manager_user):
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                          user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
    serial = uuid.uuid4()

    send_order_to_kitchen(pedido, manager_user, client_batch_serial=str(serial))

    assert pedido.batches.get().pk == id_do_lote(serial)


def test_rodada_da_comanda_com_serial_tem_id_calculado(contexto_tenant, account, restaurant, branch,
                                                       produto, manager_user):
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=31)
    launch_item(command=comanda, product=produto, user=manager_user)
    serial = uuid.uuid4()

    lote = send_command_to_kitchen(comanda, manager_user, client_batch_serial=str(serial))

    assert lote.pk == id_do_lote(serial)
