from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

from apps.menu.models import Product, ProductCategory
from apps.orders.models import CommandItem, Order, OrderItem
from apps.restaurants.models import Command


@pytest.fixture
def product(account, restaurant, branch):
    category = ProductCategory.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Lanches"
    )
    return Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        category=category,
        name="X-Burger",
        internal_code="XB001",
        sale_price=Decimal("25.00"),
        estimated_cost=Decimal("9.00"),
        controls_stock=True,
        production_sector=Product.SECTOR_KITCHEN,
    )


@pytest.mark.django_db
def test_waiter_report_uses_code_from_command_item_not_cashier_login(
    api_client, account, restaurant, branch, manager_user, product
):
    """Cobrar a comanda não pode trocar a autoria do item pelo login do caixa."""
    order = Order.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        sequence=512,
        order_type=Order.TYPE_COMMAND,
        status=Order.STATUS_PAID,
        payment_status=Order.PAYMENT_PAID,
        responsible_user=manager_user,
        closed_by=manager_user,
        total="25.00",
    )
    command = Command.objects.create(account=account, restaurant=restaurant, branch=branch)
    waiter = get_user_model().objects.create_user(username="waiter-lancador", password="secret123")
    annotation = CommandItem.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        command=command,
        product=product,
        quantity="1.000",
        unit_price="25.00",
        total_price="25.00",
        production_sector=product.production_sector,
        launched_by=waiter,
        metafields={"operator_code": "4821"},
    )
    OrderItem.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        order=order,
        command=command,
        command_item=annotation,
        product=product,
        quantity="1.000",
        unit_price="25.00",
        total_price="25.00",
        production_sector=product.production_sector,
        status=OrderItem.STATUS_DELIVERED,
        launched_by=manager_user,
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    response = api_client.get("/api/v1/reports/waiters/")

    assert response.status_code == 200
    [operator] = response.data["by_waiter"]
    assert operator["operator_code"] == "4821"
    assert operator["operator_name"] == ""
    assert operator["operator_username"] == ""
    assert operator["total"] == Decimal("25.00")
    assert operator["count"] == 1
    assert operator["items"] == 1
