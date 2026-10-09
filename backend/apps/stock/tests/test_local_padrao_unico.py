"""Dois caixas pagando juntos não podem travar todo pagamento seguinte.

A baixa de estoque do pagamento pega o local "Principal" com `get_or_create`.
Pedido sem filial: a trava única do local é (filial, nome), e no PostgreSQL
filial NULA não colide — os três caixas da simulação do dia a dia
(`loadtest/dia_a_dia`) criaram três "Principal" no mesmo instante. A partir
daí `get_or_create` levantava `MultipleObjectsReturned` e TODO recebimento da
loja dava 500.
"""
import pytest

from apps.core.tenant import tenant_context
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.stock.models import StockLocation
from apps.stock.services.order_stock import _default_location

pytestmark = pytest.mark.django_db


def test_com_principais_repetidos_usa_o_mais_antigo_em_vez_de_quebrar(
    account, restaurant, manager_user
):
    with tenant_context(account):
        pedido = create_order(restaurant=restaurant, branch=None, order_type=Order.TYPE_COUNTER,
                              user=manager_user)
        primeiro = StockLocation.objects.create(account=account, restaurant=restaurant,
                                                branch=None, name="Principal")
        StockLocation.objects.create(account=account, restaurant=restaurant, branch=None,
                                     name="Principal")

        assert _default_location(pedido, manager_user) == primeiro


def test_sem_local_cria_um_so(account, restaurant, manager_user):
    with tenant_context(account):
        pedido = create_order(restaurant=restaurant, branch=None, order_type=Order.TYPE_COUNTER,
                              user=manager_user)
        a = _default_location(pedido, manager_user)
        b = _default_location(pedido, manager_user)

        assert a == b
        assert StockLocation.objects.filter(restaurant=restaurant, name="Principal").count() == 1
