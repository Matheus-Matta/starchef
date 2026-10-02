"""O KDS mostra só produto por unidade: o prato por peso já está servido."""
from decimal import Decimal

import pytest

from apps.menu.models import Product
from apps.orders.command_items import launch_item
from apps.orders.command_kitchen import send_command_to_kitchen
from apps.orders.models import CommandItem, Order, OrderItem
from apps.orders.services import add_order_item, create_order, send_order_to_kitchen
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db
KDS = "/api/v1/kitchen/items/"


@pytest.fixture
def por_quilo(account, restaurant, branch, categoria):
    # Setor de cozinha de propósito: sem a regra, ele iria para o KDS.
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, category=categoria,
        name="Self-service", internal_code="KG001", sale_price=Decimal("59.90"),
        pricing_unit=Product.PRICING_KG, production_sector=Product.SECTOR_KITCHEN,
    )


def _balcao(restaurant, branch, user, *itens):
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=user)
    for produto, extra in itens:
        add_order_item(order=pedido, product=produto, user=user, **extra)
    return pedido


def _nomes_no_kds(api_client):
    resposta = api_client.get(KDS, {"page_size": 100})
    assert resposta.status_code == 200, resposta.content
    linhas = resposta.data["results"] if isinstance(resposta.data, dict) else resposta.data
    return sorted(linha["product_name"] for linha in linhas)


def test_balcao_manda_so_a_unidade_para_o_kds(
    contexto_tenant, api_client, restaurant, branch, manager_user, produto, por_quilo
):
    pedido = _balcao(restaurant, branch, manager_user, (produto, {"quantity": 1}),
                     (por_quilo, {"weight_kg": Decimal("0.480")}))

    send_order_to_kitchen(pedido, manager_user)

    prato = OrderItem.all_objects.get(order=pedido, product=por_quilo)
    assert prato.status == OrderItem.STATUS_DELIVERED
    assert prato.sent_to_kitchen_at is not None, "saiu: cancelar depois exige autorização"
    assert OrderItem.all_objects.get(order=pedido, product=produto).status == OrderItem.STATUS_SENT
    assert _nomes_no_kds(api_client) == [produto.name]


def test_pedido_so_de_peso_nao_fica_preso_em_producao(
    contexto_tenant, api_client, restaurant, branch, manager_user, por_quilo
):
    """Antes o prato "enviado" para sempre impedia o pedido de chegar a pronto."""
    pedido = _balcao(restaurant, branch, manager_user, (por_quilo, {"weight_kg": Decimal("0.300")}))

    send_order_to_kitchen(pedido, manager_user)

    pedido.refresh_from_db()
    assert pedido.production_status == Order.PROD_DELIVERED
    assert _nomes_no_kds(api_client) == []


def test_prato_da_balanca_na_comanda_nao_vai_ao_kds(
    contexto_tenant, restaurant, branch, manager_user, produto, por_quilo
):
    """Na cobrança o item do pedido HERDA o estado da comanda: o prato pesado
    "enviado" aparecia no KDS na hora de fechar a conta."""
    comanda = Command.objects.create(account=restaurant.account, restaurant=restaurant, branch=branch, number=77)
    prato = launch_item(command=comanda, product=por_quilo, user=manager_user, quantity=Decimal("0.450"))
    bebida = launch_item(command=comanda, product=produto, user=manager_user)

    send_command_to_kitchen(comanda, manager_user)

    prato.refresh_from_db()
    bebida.refresh_from_db()
    assert (prato.status, bebida.status) == (CommandItem.STATUS_DELIVERED, CommandItem.STATUS_SENT)
    assert prato.sent_to_kitchen_at is not None


def test_item_por_peso_antigo_ja_enviado_sai_do_quadro(
    contexto_tenant, api_client, restaurant, branch, manager_user, produto, por_quilo
):
    """Rede de segurança para o que foi enviado antes desta regra."""
    pedido = _balcao(restaurant, branch, manager_user, (produto, {"quantity": 1}),
                     (por_quilo, {"weight_kg": Decimal("0.200")}))
    OrderItem.all_objects.filter(order=pedido).update(status=OrderItem.STATUS_SENT)
    Order.all_objects.filter(pk=pedido.pk).update(production_status=Order.PROD_SENT)

    assert _nomes_no_kds(api_client) == [produto.name]
