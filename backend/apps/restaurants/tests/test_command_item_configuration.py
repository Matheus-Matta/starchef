from decimal import Decimal
import uuid

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product, ProductAddon, ProductCategory, ProductVariation
from apps.orders.command_billing import attach_commands_to_order
from apps.orders.models import CommandItem
from apps.orders.services import create_order
from apps.orders.models import Order
from apps.restaurants.models import Command


pytestmark = pytest.mark.django_db


def test_lancamento_da_comanda_grava_variacao_adicional_e_peso(
    api_client,
    account,
    restaurant,
    branch,
    manager_user,
):
    """A escolha feita no modal precisa chegar inteira à cozinha e à conta."""
    comanda = Command.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        number=13,
        code="CMD-0013",
    )
    categoria = ProductCategory.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Carnes",
    )
    produto = Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        category=categoria,
        name="Picanha",
        internal_code=f"PIC-{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("25.00"),
        production_sector=Product.SECTOR_KITCHEN,
    )
    variacao = ProductVariation.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        product=produto,
        name="Ao ponto",
        price_delta=Decimal("2.00"),
    )
    adicional = ProductAddon.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Bacon",
        price=Decimal("3.00"),
    )
    adicional.products.add(produto)

    resposta = api_client.post(
        f"/api/v1/commands/{comanda.pk}/items/",
        {
            "product": str(produto.pk),
            "quantity": "0.750",
            "variations": [str(variacao.pk)],
            "addons": [str(adicional.pk)],
            "customer_note": "Sem sal",
        },
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    with tenant_context(account):
        item = CommandItem.objects.get(pk=resposta.data["id"])
        assert item.quantity == Decimal("0.750")
        assert item.unit_price == Decimal("30.00")
        assert item.total_price == Decimal("22.50")
        assert item.variations == [{"id": str(variacao.pk), "name": "Ao ponto", "price_delta": "2.00"}]
        assert resposta.data["addons"][0]["addon_name"] == "Bacon"
        assert item.addons.get().total_price == Decimal("2.25")

        pedido = create_order(
            restaurant=restaurant,
            branch=branch,
            order_type=Order.TYPE_COUNTER,
            user=manager_user,
        )
        [item_do_pedido] = attach_commands_to_order(
            order=pedido,
            command_ids=[comanda.pk],
            user=manager_user,
        )
        assert item_do_pedido.addons.get().addon_id == adicional.pk
        assert item_do_pedido.addons.get().total_price == Decimal("2.25")
