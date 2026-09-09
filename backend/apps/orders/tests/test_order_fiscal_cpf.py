import uuid
from decimal import Decimal

import pytest

from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db


def _order(account, restaurant, branch, user, *, sale_price=Decimal("10.00")):
    product = Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Produto CPF",
        internal_code=f"CPF-{uuid.uuid4().hex[:6]}",
        sale_price=sale_price,
    )
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=user,
    )
    add_order_item(order=order, product=product, quantity=1, user=user)
    return order


def test_close_stores_normalized_cpf_for_the_invoice(
    api_client, account, restaurant, branch, manager_user
):
    order = _order(account, restaurant, branch, manager_user)

    response = api_client.post(
        f"/api/v1/orders/{order.id}/close/",
        {"service_fee_enabled": False, "fiscal_customer_cpf": "123.456.789-09"},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["fiscal_customer_cpf"] == "12345678909"


def test_close_rejects_invalid_cpf(api_client, account, restaurant, branch, manager_user):
    order = _order(account, restaurant, branch, manager_user)

    response = api_client.post(
        f"/api/v1/orders/{order.id}/close/",
        {"service_fee_enabled": False, "fiscal_customer_cpf": "111.111.111-11"},
        format="json",
    )

    assert response.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_OPEN
    assert order.fiscal_customer_cpf == ""


def test_close_reconciles_client_total_with_authoritative_total(
    api_client, account, restaurant, branch, manager_user
):
    restaurant.default_service_fee_percent = Decimal("10.00")
    restaurant.save(update_fields=["default_service_fee_percent"])
    order = _order(
        account,
        restaurant,
        branch,
        manager_user,
        sale_price=Decimal("43.15"),
    )

    response = api_client.post(
        f"/api/v1/orders/{order.id}/close/",
        {
            "service_fee_enabled": True,
            "expected_total": "47.46",
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["total_reconciled"] is True
    assert response.data["client_expected_total"] == "47.46"
    assert response.data["authoritative_total"] == "47.47"
    assert response.data["total"] == "47.47"
