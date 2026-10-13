"""A resposta da venda leva só o que o PDV lê do item.

O item vinha com 49 campos, e 15 deles nenhum PDV lê: o pedido repetido em
cada linha (número, tipo, situações), a posição no KDS, quem criou/editou.
Em 50 itens eram 68 KB por resposta, montados e enviados com o caixa
esperando. O resto do sistema (KDS, painel) segue com o item completo.
"""
import pytest

from apps.orders.serializers import CAMPOS_FORA_DA_VENDA
from apps.orders.tests.test_venda_inteira import URL, _venda

pytestmark = pytest.mark.django_db


def test_itens_da_resposta_da_venda_vem_enxutos(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, produto, dinheiro
):
    corpo = dict(_venda(restaurant, produto, dinheiro, itens=2), simular=True, payments=[])

    item = api_client.post(URL, corpo, format="json").json()["order"]["items"][0]

    assert not set(item) & CAMPOS_FORA_DA_VENDA
    # O que o PDV usa continua: tela, recibo e nota.
    assert {"id", "product", "product_name", "quantity", "unit_price", "total_price",
            "addons", "variations", "status", "pricing_unit"} <= set(item)


def test_fora_da_venda_o_item_continua_completo(api_client, contexto_tenant, restaurant, produto, manager_user):
    from apps.orders.models import Order
    from apps.orders.services import add_order_item, create_order

    pedido = create_order(restaurant=restaurant, order_type=Order.TYPE_COUNTER, user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)

    item = api_client.get(f"/api/v1/orders/{pedido.pk}/").json()["items"][0]

    assert CAMPOS_FORA_DA_VENDA <= set(item)
