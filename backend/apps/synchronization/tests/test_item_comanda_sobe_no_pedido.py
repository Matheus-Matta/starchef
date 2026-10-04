"""A cobrança da comanda precisa mandar os itens junto com o pedido."""
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product, ProductAddon, ProductCategory
from apps.orders.command_billing import attach_commands_to_order
from apps.orders.command_item_launch import launch_item
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.restaurants.models import Command
from apps.synchronization.models import SyncEvent

pytestmark = pytest.mark.django_db


def test_item_anexado_a_comanda_gera_evento_com_dependencia_do_pedido(
    como_loja, account, restaurant, branch, manager_user
):
    """`bulk_create` não dispara signal; sem outbox explícita a nuvem só recebe o pedido vazio."""
    categoria = ProductCategory.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Lanches"
    )
    produto = Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        category=categoria,
        name="X-Burger",
        internal_code="SYNC-XBURGER",
        sale_price=Decimal("25.00"),
        production_sector=Product.SECTOR_KITCHEN,
    )
    adicional = ProductAddon.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Bacon",
        price=Decimal("4.00"),
    )
    comanda = Command.objects.create(
        account=account, restaurant=restaurant, branch=branch, number=41
    )
    with tenant_context(account):
        adicional.products.add(produto)
        anotacao = launch_item(
            command=comanda,
            product=produto,
            user=manager_user,
            addons=[str(adicional.pk)],
        )
    pedido = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=manager_user,
    )

    [item] = attach_commands_to_order(
        order=pedido, command_ids=[comanda.pk], user=manager_user
    )

    evento = SyncEvent.objects.get(entity_type="order_item", entity_id=str(item.pk))
    assert evento.payload["fields"]["order_id"] == str(pedido.pk)
    assert evento.payload["fields"]["command_item_id"] == str(anotacao.pk)
    evento_adicional = SyncEvent.objects.get(entity_type="order_item_addon")
    assert evento_adicional.payload["fields"]["item_id"] == str(item.pk)
    assert evento_adicional.payload["fields"]["addon_id"] == str(adicional.pk)
