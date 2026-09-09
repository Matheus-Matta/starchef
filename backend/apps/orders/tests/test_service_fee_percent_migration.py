"""A migration 0006 realinha os pedidos que ficaram com a taxa congelada.

O passo de dados e exercitado diretamente, com um registro que imita o que uma
migration recebe: managers sem escopo de tenant. Rodar o executor de migrations
inteiro custaria minutos e provaria o mesmo.
"""

import uuid
from decimal import Decimal
from importlib import import_module

import pytest

from apps.menu.models import Product
from apps.orders.models import Order, OrderItem
from apps.orders.services import add_order_item, close_order, create_order

pytestmark = pytest.mark.django_db

repair_totals = import_module("apps.orders.migrations.0006_order_service_fee_percent").repair_totals


class _HistoricalRegistry:
    """`apps` de migration: `Model.objects` sem o filtro de tenant."""

    def __init__(self, **models):
        self._models = models

    def get_model(self, _app_label, name):
        return self._models[name]


class _Historical:
    def __init__(self, model):
        self.objects = model.all_objects


@pytest.fixture
def product(account, restaurant, branch):
    return Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Produto migration",
        internal_code=f"MIG-{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("20.00"),
    )


def _registry():
    return _HistoricalRegistry(Order=_Historical(Order), OrderItem=_Historical(OrderItem))


def test_frozen_fee_is_realigned_with_the_current_subtotal(
    restaurant, branch, product, manager_user
):
    restaurant.default_service_fee_percent = Decimal("10.00")
    restaurant.save(update_fields=["default_service_fee_percent"])
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    order = close_order(order, manager_user)
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    # Volta ao estado que ficou no banco: taxa de R$ 2,00 (10% de UM item) com
    # subtotal de dois itens, e aliquota desconhecida.
    Order.all_objects.filter(pk=order.pk).update(
        service_fee_percent=None,
        service_fee=Decimal("2.00"),
        total=Decimal("42.00"),
    )

    repair_totals(_registry(), None)

    order.refresh_from_db()
    assert order.subtotal == Decimal("40.00")
    assert order.service_fee_percent == Decimal("10.00")
    assert order.service_fee == Decimal("4.00")
    assert order.total == Decimal("44.00")


def test_order_without_service_fee_stays_without_it(restaurant, branch, product, manager_user):
    restaurant.default_service_fee_percent = Decimal("10.00")
    restaurant.save(update_fields=["default_service_fee_percent"])
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    order = close_order(order, manager_user, service_fee_enabled=False)

    repair_totals(_registry(), None)

    order.refresh_from_db()
    assert order.service_fee == Decimal("0.00")
    assert order.service_fee_percent is None
    assert order.total == order.subtotal


def test_open_order_keeps_the_fee_out_of_the_cart(restaurant, branch, product, manager_user):
    """Pedido aberto nao ganha taxa: ela nasce no fechamento, nao antes."""
    restaurant.default_service_fee_percent = Decimal("10.00")
    restaurant.save(update_fields=["default_service_fee_percent"])
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=1, user=manager_user)

    repair_totals(_registry(), None)

    order.refresh_from_db()
    assert order.status == Order.STATUS_OPEN
    assert order.service_fee == Decimal("0.00")
    assert order.service_fee_percent is None
    assert order.total == order.subtotal


def test_paid_order_is_left_alone(account, restaurant, branch, product, manager_user):
    from apps.payments.models import PaymentMethod
    from apps.payments.services import open_cash_register, register_payment

    restaurant.default_service_fee_percent = Decimal("10.00")
    restaurant.save(update_fields=["default_service_fee_percent"])
    method = PaymentMethod.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Dinheiro",
        method_type=PaymentMethod.TYPE_CASH,
    )
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    order = close_order(order, manager_user)
    open_cash_register(branch=branch, user=manager_user)
    register_payment(
        order=order,
        user=manager_user,
        payment_method_id=method.id,
        amount=order.total,
    )
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID
    before = (order.subtotal, order.service_fee, order.total)
    Order.all_objects.filter(pk=order.pk).update(service_fee_percent=None)

    repair_totals(_registry(), None)

    order.refresh_from_db()
    assert (order.subtotal, order.service_fee, order.total) == before
    assert order.service_fee_percent is None
