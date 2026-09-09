"""O comando que conserta os pedidos que ficaram com o total errado no banco."""

import uuid
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, close_order, create_order

pytestmark = pytest.mark.django_db


@pytest.fixture
def product(account, restaurant, branch):
    return Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Produto reparo",
        internal_code=f"REP-{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("21.55"),
    )


def _closed_order_with_frozen_fee(restaurant, branch, product, user):
    """Reproduz o estado que ficou no banco: taxa presa no subtotal antigo."""
    restaurant.default_service_fee_percent = Decimal("10.00")
    restaurant.save(update_fields=["default_service_fee_percent"])
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=user,
    )
    add_order_item(order=order, product=product, quantity=1, user=user)
    order = close_order(order, user)
    add_order_item(order=order, product=product, quantity=1, user=user)
    # Desfaz a correcao para ficar exatamente como os pedidos antigos: aliquota
    # desconhecida e taxa parada no subtotal de um item.
    order.refresh_from_db()
    frozen_fee = (product.current_price * Decimal("0.10")).quantize(Decimal("0.01"))
    Order.all_objects.filter(pk=order.pk).update(
        service_fee_percent=None,
        service_fee=frozen_fee,
        total=order.subtotal + frozen_fee,
    )
    order.refresh_from_db()
    return order, frozen_fee


def test_reports_without_writing_by_default(restaurant, branch, product, manager_user):
    order, frozen_fee = _closed_order_with_frozen_fee(restaurant, branch, product, manager_user)

    out = StringIO()
    call_command("repair_order_totals", "--order", str(order.pk), "--adopt-restaurant-percent", stdout=out)

    assert str(order.pk) in out.getvalue()
    order.refresh_from_db()
    assert order.service_fee == frozen_fee


def test_apply_puts_the_fee_back_on_the_current_subtotal(restaurant, branch, product, manager_user):
    order, _ = _closed_order_with_frozen_fee(restaurant, branch, product, manager_user)

    call_command(
        "repair_order_totals",
        "--order",
        str(order.pk),
        "--adopt-restaurant-percent",
        "--apply",
        stdout=StringIO(),
    )

    order.refresh_from_db()
    expected_fee = (order.subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
    assert order.service_fee_percent == Decimal("10.00")
    assert order.service_fee == expected_fee
    assert order.total == order.subtotal + expected_fee


def test_paid_orders_are_never_touched(account, restaurant, branch, product, manager_user):
    from apps.payments.models import PaymentMethod
    from apps.payments.services import open_cash_register, register_payment

    payment_method = PaymentMethod.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Dinheiro",
        method_type=PaymentMethod.TYPE_CASH,
    )

    order, _ = _closed_order_with_frozen_fee(restaurant, branch, product, manager_user)
    open_cash_register(branch=branch, user=manager_user)
    register_payment(
        order=order,
        user=manager_user,
        payment_method_id=payment_method.id,
        amount=order.total,
    )
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID
    before = (order.subtotal, order.service_fee, order.total)

    with pytest.raises(Exception):
        call_command(
            "repair_order_totals",
            "--order",
            str(order.pk),
            "--adopt-restaurant-percent",
            "--apply",
            stdout=StringIO(),
        )

    order.refresh_from_db()
    assert (order.subtotal, order.service_fee, order.total) == before
