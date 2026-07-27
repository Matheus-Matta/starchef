from decimal import Decimal

import pytest

from apps.menu.models import Product
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
