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


def test_list_expoe_o_restaurante_de_cada_forma_de_pagamento(admin_client, account, restaurant):
    """Com mais de um restaurante a conta tem métodos homônimos (todo restaurante
    nasce com o mesmo conjunto padrão): a listagem precisa dizer de quem é cada um."""
    outro = Restaurant.objects.create(
        account=account,
        legal_name="Segunda Casa Ltda",
        trade_name="Segunda Casa",
    )

    resp = admin_client.get("/api/v1/payments/methods/")

    assert resp.status_code == 200, resp.data
    por_restaurante = {}
    for row in resp.data["results"]:
        assert row["restaurant_name"], "toda forma de pagamento tem restaurante nomeado"
        por_restaurante.setdefault(row["restaurant_name"], set()).add(row["name"])
    assert {restaurant.trade_name, outro.trade_name} <= set(por_restaurante)
    # Homônimos entre restaurantes: o nome sozinho não distingue, o restaurante sim.
    assert por_restaurante[restaurant.trade_name] == por_restaurante[outro.trade_name]


def test_filtro_por_restaurante_separa_as_formas(admin_client, account, restaurant):
    outro = Restaurant.objects.create(
        account=account,
        legal_name="Terceira Casa Ltda",
        trade_name="Terceira Casa",
    )

    resp = admin_client.get("/api/v1/payments/methods/", {"restaurant": str(outro.id)})

    assert resp.status_code == 200, resp.data
    nomes = {row["restaurant_name"] for row in resp.data["results"]}
    assert nomes == {outro.trade_name}
