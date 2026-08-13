import pytest

from apps.core.tenant import tenant_context
from apps.payments.defaults import DEFAULT_PAYMENT_METHODS, ensure_default_payment_methods
from apps.payments.models import PaymentMethod
from apps.restaurants.models import Restaurant


pytestmark = pytest.mark.django_db


def test_new_restaurant_gets_default_payment_methods(account):
    restaurant = Restaurant.objects.create(
        account=account,
        legal_name="Nova Cozinha Ltda",
        trade_name="Nova Cozinha",
    )

    with tenant_context(account):
        methods = PaymentMethod.objects.filter(restaurant=restaurant)
        assert set(methods.values_list("name", "method_type")) == set(DEFAULT_PAYMENT_METHODS)
        assert methods.filter(is_active=True).count() == len(DEFAULT_PAYMENT_METHODS)


def test_default_payment_method_provisioning_is_idempotent(restaurant):
    ensure_default_payment_methods(restaurant=restaurant)
    ensure_default_payment_methods(restaurant=restaurant)

    with tenant_context(restaurant.account):
        assert PaymentMethod.objects.filter(restaurant=restaurant).count() == len(DEFAULT_PAYMENT_METHODS)
