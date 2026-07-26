from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import AccessToken

from apps.orders.models import Order
from apps.orders.services import add_order_item, cancel_order, close_order, create_order
from apps.payments.services import open_cash_register, register_payment
from apps.restaurants.models import Command
from apps.restaurants.services import next_command_number


@pytest.mark.django_db
def test_command_auto_number_and_code_per_restaurant(account, restaurant, branch):
    first = Command.objects.create(account=account, restaurant=restaurant, branch=branch)
    second = Command.objects.create(account=account, restaurant=restaurant, branch=branch)

    assert first.number == 1
    assert second.number == 2
    # code escaneável padrão = número zero-padded.
    assert first.code == "0001"
    assert second.code == "0002"
    assert next_command_number(restaurant) == 3


@pytest.mark.django_db
def test_opening_command_order_occupies_it(restaurant, branch, command, product, waiter_user):
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COMMAND,
        command=command,
        user=waiter_user,
    )
    add_order_item(order=order, product=product, quantity=1, user=waiter_user)
    command.refresh_from_db()

    assert order.command_id == command.id
    assert command.status == Command.STATUS_OCCUPIED
    assert command.current_order_id == order.id


@pytest.mark.django_db
def test_occupied_command_cannot_open_second_order(restaurant, branch, command, product, waiter_user):
    create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND, command=command, user=waiter_user)

    with pytest.raises(ValidationError):
        create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND, command=command, user=waiter_user)


@pytest.mark.django_db
def test_payment_frees_and_resets_command(restaurant, branch, command, product, payment_method, manager_user):
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND, command=command, user=manager_user)
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    order = close_order(order, manager_user)
    open_cash_register(branch=branch, user=manager_user, opening_amount=Decimal("100.00"))

    register_payment(order=order, user=manager_user, payment_method_id=payment_method.id, amount=order.total)
    command.refresh_from_db()

    # Zerada e livre para reuso; o número/código do cartão permanecem.
    assert command.status == Command.STATUS_FREE
    assert command.current_order_id is None
    assert command.customer_name == ""
    assert command.number == 1


@pytest.mark.django_db
def test_bulk_create_via_api(api_client, restaurant, manager_user):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    response = api_client.post(
        "/api/v1/commands/bulk-create/",
        {"restaurant": str(restaurant.id), "to_number": 200},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["created"] == 200
    assert Command.all_objects.filter(restaurant=restaurant).count() == 200

    # Reexecutar o mesmo intervalo pula os já existentes.
    again = api_client.post(
        "/api/v1/commands/bulk-create/",
        {"restaurant": str(restaurant.id), "from_number": 1, "to_number": 200},
        format="json",
    )
    assert again.status_code == 201
    assert again.data["created"] == 0
    assert again.data["skipped"] == 200
    assert Command.all_objects.filter(restaurant=restaurant).count() == 200


@pytest.mark.django_db
def test_cancel_frees_command(restaurant, branch, command, product, manager_user):
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND, command=command, user=manager_user)
    add_order_item(order=order, product=product, quantity=1, user=manager_user)

    cancel_order(order, manager_user, reason="cliente desistiu")
    command.refresh_from_db()

    assert command.status == Command.STATUS_FREE
    assert command.current_order_id is None
