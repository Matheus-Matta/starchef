from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import Payment, PaymentMethod
from apps.payments.services import register_payment

pytestmark = pytest.mark.django_db


@pytest.fixture
def payable_order(account, restaurant, branch, manager_user):
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    product = Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Refrigerante",
        internal_code="REF-CARD",
        sale_price=Decimal("7.00"),
    )
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=manager_user,
    )
    add_order_item(
        order=order,
        product=product,
        quantity=1,
        user=manager_user,
    )
    order.refresh_from_db()
    return order


@pytest.fixture
def card_method(account, restaurant, branch):
    return PaymentMethod.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Cartao",
        method_type=PaymentMethod.TYPE_CARD,
    )


def test_register_payment_persists_credit_subtype(
    payable_order, card_method, manager_user
):
    payment = register_payment(
        order=payable_order,
        user=manager_user,
        payment_method_id=card_method.id,
        amount=payable_order.total,
        metadata={"card_subtype": "credit", "source": "flutter_pdv"},
    )

    assert payment.card_subtype == Payment.CARD_CREDIT
    assert payment.metadata["card_subtype"] == Payment.CARD_CREDIT


def test_register_payment_rejects_card_without_subtype(
    payable_order, card_method, manager_user
):
    with pytest.raises(ValidationError, match="débito ou crédito"):
        register_payment(
            order=payable_order,
            user=manager_user,
            payment_method_id=card_method.id,
            amount=payable_order.total,
            metadata={},
        )
