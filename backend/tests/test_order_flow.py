from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.orders.models import Order, OrderItem
from apps.orders.services import add_order_item, close_order, create_order, send_order_to_kitchen, update_order_item_status
from apps.payments.models import PaymentMethod
from apps.payments.services import cancel_payment, open_cash_register, register_payment
from apps.restaurants.models import Table
from apps.stock.models import StockMovement


@pytest.mark.django_db
def test_product_creation(product):
    assert product.name == "X-Burger"
    assert product.sale_price == Decimal("25.00")
    assert product.production_sector == "kitchen"


@pytest.mark.django_db
def test_create_order_and_send_to_kitchen(restaurant, branch, table, product, waiter_user):
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_TABLE,
        table=table,
        user=waiter_user,
    )
    item = add_order_item(order=order, product=product, quantity=2, user=waiter_user)

    send_order_to_kitchen(order, waiter_user)
    item.refresh_from_db()
    order.refresh_from_db()
    table.refresh_from_db()

    assert order.status == Order.STATUS_OPEN
    assert order.production_status == Order.PROD_SENT
    assert item.status == OrderItem.STATUS_SENT
    assert item.sent_to_kitchen_at is not None
    assert item.batch is not None
    assert table.status == Table.STATUS_OCCUPIED


@pytest.mark.django_db
def test_change_kitchen_item_status(restaurant, branch, table, product, manager_user):
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_TABLE, table=table, user=manager_user)
    item = add_order_item(order=order, product=product, quantity=1, user=manager_user)
    send_order_to_kitchen(order, manager_user)

    update_order_item_status(item, OrderItem.STATUS_PREPARING, manager_user)
    update_order_item_status(item, OrderItem.STATUS_READY, manager_user)
    item.refresh_from_db()
    order.refresh_from_db()

    assert item.status == OrderItem.STATUS_READY
    assert item.ready_at is not None
    assert order.production_status == Order.PROD_READY


@pytest.mark.django_db
def test_payment_closes_order_releases_table_and_deducts_stock(
    restaurant,
    branch,
    table,
    product_with_recipe,
    payment_method,
    manager_user,
):
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_TABLE, table=table, user=manager_user)
    add_order_item(order=order, product=product_with_recipe, quantity=1, user=manager_user)
    order = close_order(order, manager_user)
    open_cash_register(branch=branch, user=manager_user, opening_amount=Decimal("100.00"))

    payment = register_payment(
        order=order,
        user=manager_user,
        payment_method_id=payment_method.id,
        amount=Decimal("27.50"),
        idempotency_key="pay-order-1",
    )

    order.refresh_from_db()
    table.refresh_from_db()

    assert payment.amount == order.total
    assert order.payment_status == Order.PAYMENT_PAID
    assert order.status == Order.STATUS_PAID
    assert table.status == Table.STATUS_FREE
    assert StockMovement.objects.filter(order_item__order=order, movement_type=StockMovement.TYPE_SALE).exists()


@pytest.mark.django_db
def test_payment_is_idempotent(restaurant, branch, table, product, payment_method, manager_user):
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_TABLE, table=table, user=manager_user)
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    order = close_order(order, manager_user)
    open_cash_register(branch=branch, user=manager_user)

    first = register_payment(
        order=order,
        user=manager_user,
        payment_method_id=payment_method.id,
        amount=order.total,
        idempotency_key="same-key",
    )
    second = register_payment(
        order=order,
        user=manager_user,
        payment_method_id=payment_method.id,
        amount=order.total,
        idempotency_key="same-key",
    )

    assert first.id == second.id


@pytest.mark.django_db
def test_cash_payment_records_received_amount_and_change(
    account, restaurant, branch, table, product, manager_user
):
    cash = PaymentMethod.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Dinheiro",
        method_type=PaymentMethod.TYPE_CASH,
    )
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_TABLE,
        table=table,
        user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=7, user=manager_user)
    order = close_order(order, manager_user)
    open_cash_register(branch=branch, user=manager_user)
    received = order.total + Decimal("25.00")

    payment = register_payment(
        order=order,
        user=manager_user,
        payment_method_id=cash.id,
        amount=received,
    )

    assert payment.amount == order.total
    assert payment.change_amount == Decimal("25.00")
    assert payment.metadata["received_amount"] == str(received)
    assert payment.metadata["applied_amount"] == str(order.total)
    assert payment.metadata["change_amount"] == "25.00"


@pytest.mark.django_db
def test_cancel_cash_payment_reopens_order_and_removes_cash_movement(
    account, restaurant, branch, table, product, manager_user
):
    cash = PaymentMethod.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Dinheiro cancelável",
        method_type=PaymentMethod.TYPE_CASH,
    )
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_TABLE,
        table=table,
        user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    order = close_order(order, manager_user)
    open_cash_register(branch=branch, user=manager_user)
    payment = register_payment(
        order=order,
        user=manager_user,
        payment_method_id=cash.id,
        amount=order.total + Decimal("10.00"),
    )

    cancel_payment(payment=payment, user=manager_user)

    payment.refresh_from_db()
    order.refresh_from_db()
    table.refresh_from_db()
    assert payment.status == payment.STATUS_CANCELLED
    assert not payment.cash_movements.filter(status="approved").exists()
    assert order.payment_status == Order.PAYMENT_PENDING
    assert order.status == Order.STATUS_AWAITING_PAYMENT
    assert table.current_order_id == order.id


@pytest.mark.django_db
def test_non_cash_payment_cannot_exceed_remaining(
    restaurant, branch, table, product, payment_method, manager_user
):
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_TABLE,
        table=table,
        user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    order = close_order(order, manager_user)
    open_cash_register(branch=branch, user=manager_user)

    with pytest.raises(ValidationError):
        register_payment(
            order=order,
            user=manager_user,
            payment_method_id=payment_method.id,
            amount=order.total + Decimal("1.00"),
        )


@pytest.mark.django_db
def test_paid_order_cannot_be_changed(restaurant, branch, table, product, payment_method, manager_user):
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_TABLE, table=table, user=manager_user)
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    order = close_order(order, manager_user)
    open_cash_register(branch=branch, user=manager_user)
    register_payment(order=order, user=manager_user, payment_method_id=payment_method.id, amount=order.total)

    with pytest.raises(ValidationError):
        add_order_item(order=order, product=product, quantity=1, user=manager_user)


@pytest.mark.django_db
def test_cancel_item_requires_reason(restaurant, branch, table, product, manager_user):
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_TABLE, table=table, user=manager_user)
    item = add_order_item(order=order, product=product, quantity=1, user=manager_user)

    with pytest.raises(ValidationError):
        update_order_item_status(item, OrderItem.STATUS_CANCELLED, manager_user)
