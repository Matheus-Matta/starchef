from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product, ProductAddon, ProductVariation
from apps.orders.models import OrderItem
from apps.printers.models import Scale, ScaleReading
from apps.restaurants.models import Command


@pytest.mark.django_db
def test_scale_checkout_command_is_atomic_and_reading_is_one_time(
    admin_client,
    account,
    restaurant,
    branch,
):
    weighed = Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Buffet",
        internal_code="BUFFET-KG",
        sale_price=Decimal("59.90"),
        pricing_unit=Product.PRICING_KG,
    )
    drink = Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Água",
        internal_code="AGUA",
        sale_price=Decimal("5.00"),
    )
    scale = Scale.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Balança buffet",
        product=weighed,
    )
    reading = ScaleReading.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        scale=scale,
        weight_kg=Decimal("0.500"),
        is_stable=True,
    )
    command = Command.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        number=10,
    )
    payload = {
        # Digitacao humana do numero tambem resolve o codigo zero-padded.
        "command_code": str(command.number),
        "scale_reading": str(reading.id),
        "extras": [{"product": str(drink.id), "quantity": 2}],
        "print": False,
    }

    response = admin_client.post(
        f"/api/v1/scales/{scale.id}/checkout-command/",
        payload,
        format="json",
    )

    assert response.status_code == 201, response.data
    assert len(response.data["order"]["items"]) == 2
    assert OrderItem.all_objects.filter(product=weighed, quantity=Decimal("0.500")).exists()
    assert OrderItem.all_objects.filter(product=drink, quantity=Decimal("2")).exists()
    reading.refresh_from_db()
    assert reading.order_item_id is not None

    replay = admin_client.post(
        f"/api/v1/scales/{scale.id}/checkout-command/",
        payload,
        format="json",
    )
    assert replay.status_code == 400
    assert OrderItem.all_objects.count() == 2


@pytest.mark.django_db
def test_scale_checkout_command_applies_extra_variation_addon_and_note(
    admin_client,
    account,
    restaurant,
    branch,
):
    """A balança rápida agora faz a mesma pergunta do PDV padrão pros extras
    (variação, adicionais, observação) — isso precisa chegar inteiro no
    servidor, não só produto e quantidade."""
    weighed = Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Buffet",
        internal_code="BUFFET-KG2",
        sale_price=Decimal("59.90"),
        pricing_unit=Product.PRICING_KG,
    )
    burger = Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Hamburguer",
        internal_code="BURGER",
        sale_price=Decimal("20.00"),
    )
    size = ProductVariation.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        product=burger, name="Grande", price_delta=Decimal("5.00"),
    )
    bacon = ProductAddon.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Bacon", price=Decimal("3.00"),
    )
    bacon.products.add(burger)
    scale = Scale.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Balança buffet 2", product=weighed,
    )
    reading = ScaleReading.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        scale=scale, weight_kg=Decimal("0.500"), is_stable=True,
    )
    command = Command.objects.create(
        account=account, restaurant=restaurant, branch=branch, number=11,
    )

    response = admin_client.post(
        f"/api/v1/scales/{scale.id}/checkout-command/",
        {
            "command_code": str(command.number),
            "scale_reading": str(reading.id),
            "extras": [
                {
                    "product": str(burger.id),
                    "quantity": 1,
                    "variations": [str(size.id)],
                    "addons": [str(bacon.id)],
                    "customer_note": "sem cebola",
                }
            ],
            "print": False,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    item = OrderItem.all_objects.get(product=burger)
    assert item.customer_note == "sem cebola"
    assert [v["id"] for v in item.variations] == [str(size.id)]
    # item.addons e um related manager escopado por tenant (TenantManager):
    # fora do contexto de conta ele filtra pela conta corrente e devolveria
    # vazio mesmo com o adicional gravado — precisa do mesmo contexto que
    # add_order_item usa para escrever.
    with tenant_context(account):
        assert {a.addon_id for a in item.addons.all()} == {bacon.id}
    # Preco unitario carrega o delta da variacao (+5) e do adicional (+3).
    assert item.unit_price == Decimal("28.00")
