from decimal import Decimal

import pytest

from apps.menu.models import Product
from apps.orders.models import OrderItem
from apps.printers.models import ScaleReading


pytestmark = pytest.mark.django_db


def _payload(restaurant, product, **item_fields):
    return {
        "order_type": "counter",
        "restaurant": str(restaurant.pk),
        "item": {"product": str(product.pk), **item_fields},
    }


def test_create_with_item_keeps_manual_weight_for_the_first_sale_item(
    contexto_tenant, api_client, restaurant, produto, sem_caixa_obrigatorio
):
    """A venda de balcão nasce com o primeiro item, então precisa repassar o peso."""
    produto.pricing_unit = Product.PRICING_KG
    produto.save(update_fields=["pricing_unit"])

    response = api_client.post(
        "/api/v1/orders/create-with-item/",
        _payload(restaurant, produto, weight_kg="0.500"),
        format="json",
    )

    assert response.status_code == 201, response.data
    item = OrderItem.all_objects.get(pk=response.data["created_item_id"])
    assert item.quantity == Decimal("0.500")
    assert item.total_price == Decimal("12.50")


def test_create_with_item_keeps_scale_reading_for_the_first_sale_item(
    contexto_tenant,
    api_client,
    account,
    restaurant,
    branch,
    produto,
    sem_caixa_obrigatorio,
):
    """A leitura da balança também tem de chegar ao serviço de criação."""
    produto.pricing_unit = Product.PRICING_KG
    produto.save(update_fields=["pricing_unit"])
    reading = ScaleReading.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        weight_kg=Decimal("0.500"),
        tare_kg=Decimal("0.000"),
        source=ScaleReading.SOURCE_MANUAL,
    )

    response = api_client.post(
        "/api/v1/orders/create-with-item/",
        _payload(restaurant, produto, scale_reading=str(reading.pk)),
        format="json",
    )

    assert response.status_code == 201, response.data
    item = OrderItem.all_objects.get(pk=response.data["created_item_id"])
    reading.refresh_from_db()
    assert item.quantity == Decimal("0.500")
    assert reading.order_item_id == item.id
