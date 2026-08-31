"""Posicao de estoque (`/stock/positions/`): a leitura por insumo.

O que a tela precisa garantir: o saldo vem do livro de movimentos, o insumo
sem nenhum movimento aparece zerado (senao ninguem descobre o que falta
comprar) e o insumo inativo so continua na lista enquanto sobrar saldo dele.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.menu.models import Ingredient
from apps.stock.models import StockLocation, StockLot, StockMovement

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant(account):
    with tenant_context(account):
        yield


@pytest.fixture
def account_with_logistica(account):
    account.enabled_modules = ["logistica"]
    account.save(update_fields=["enabled_modules"])
    return account


@pytest.fixture
def location(account, restaurant, branch, manager_user):
    return StockLocation.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Deposito",
        created_by=manager_user, updated_by=manager_user,
    )


def _ingredient(account, restaurant, branch, user, name, **kwargs):
    return Ingredient.objects.create(
        account=account, restaurant=restaurant, branch=branch, name=name,
        unit=kwargs.pop("unit", "kg"), created_by=user, updated_by=user, **kwargs,
    )


def _movement(account, restaurant, branch, user, location, ingredient, quantity, **kwargs):
    return StockMovement.objects.create(
        account=account, restaurant=restaurant, branch=branch, location=location,
        ingredient=ingredient, operator=user, movement_type=kwargs.pop("movement_type", StockMovement.TYPE_IN),
        quantity=Decimal(quantity), created_by=user, updated_by=user, **kwargs,
    )


def _positions(response):
    return {row["ingredient_name"]: row for row in response.json()["positions"]}


def test_requires_logistica_module(api_client):
    assert api_client.get("/api/v1/stock/positions/").status_code == 403


def test_lists_ingredient_without_movement_as_zero(
    api_client, account_with_logistica, restaurant, branch, manager_user
):
    _ingredient(account_with_logistica, restaurant, branch, manager_user, "Farinha")

    response = api_client.get("/api/v1/stock/positions/")

    assert response.status_code == 200
    row = _positions(response)["Farinha"]
    assert Decimal(row["balance"]) == Decimal("0")
    assert row["situation"] == "out"


def test_balance_is_the_sum_of_movements_and_breaks_down_by_location(
    api_client, account_with_logistica, restaurant, branch, manager_user, location
):
    ingredient = _ingredient(account_with_logistica, restaurant, branch, manager_user, "Arroz")
    other = StockLocation.objects.create(
        account=account_with_logistica, restaurant=restaurant, branch=branch, name="Cozinha",
        created_by=manager_user, updated_by=manager_user,
    )
    _movement(account_with_logistica, restaurant, branch, manager_user, location, ingredient, "10")
    _movement(account_with_logistica, restaurant, branch, manager_user, location, ingredient, "-4",
              movement_type=StockMovement.TYPE_OUT)
    _movement(account_with_logistica, restaurant, branch, manager_user, other, ingredient, "3")

    row = _positions(api_client.get("/api/v1/stock/positions/"))["Arroz"]

    assert Decimal(row["balance"]) == Decimal("9")
    assert {item["location_name"]: Decimal(item["balance"]) for item in row["locations"]} == {
        "Deposito": Decimal("6"),
        "Cozinha": Decimal("3"),
    }


def test_location_filter_narrows_the_balance(
    api_client, account_with_logistica, restaurant, branch, manager_user, location
):
    ingredient = _ingredient(account_with_logistica, restaurant, branch, manager_user, "Arroz")
    other = StockLocation.objects.create(
        account=account_with_logistica, restaurant=restaurant, branch=branch, name="Cozinha",
        created_by=manager_user, updated_by=manager_user,
    )
    _movement(account_with_logistica, restaurant, branch, manager_user, location, ingredient, "6")
    _movement(account_with_logistica, restaurant, branch, manager_user, other, ingredient, "3")

    response = api_client.get("/api/v1/stock/positions/", {"location": str(location.id)})

    row = _positions(response)["Arroz"]
    assert Decimal(row["balance"]) == Decimal("6")


def test_below_minimum_is_flagged_as_low(
    api_client, account_with_logistica, restaurant, branch, manager_user, location
):
    ingredient = _ingredient(
        account_with_logistica, restaurant, branch, manager_user, "Sal", minimum_stock=Decimal("5"),
    )
    _movement(account_with_logistica, restaurant, branch, manager_user, location, ingredient, "2")

    response = api_client.get("/api/v1/stock/positions/")

    assert _positions(response)["Sal"]["situation"] == "low"
    assert response.json()["totals"]["low"] == 1


def test_inactive_ingredient_only_shows_while_it_still_has_balance(
    api_client, account_with_logistica, restaurant, branch, manager_user, location
):
    empty = _ingredient(account_with_logistica, restaurant, branch, manager_user, "Aposentado", is_active=False)
    leftover = _ingredient(account_with_logistica, restaurant, branch, manager_user, "Sobrou", is_active=False)
    _movement(account_with_logistica, restaurant, branch, manager_user, location, leftover, "2")

    names = _positions(api_client.get("/api/v1/stock/positions/")).keys()

    assert leftover.name in names
    assert empty.name not in names


def test_stock_value_uses_the_average_cost(
    api_client, account_with_logistica, restaurant, branch, manager_user, location
):
    ingredient = _ingredient(
        account_with_logistica, restaurant, branch, manager_user, "Queijo", average_cost=Decimal("12.50"),
    )
    _movement(account_with_logistica, restaurant, branch, manager_user, location, ingredient, "4")

    response = api_client.get("/api/v1/stock/positions/")

    assert Decimal(_positions(response)["Queijo"]["stock_value"]) == Decimal("50.00")
    assert Decimal(response.json()["totals"]["stock_value"]) == Decimal("50.00")


def test_next_expiry_is_the_nearest_lot_not_the_farthest(
    api_client, account_with_logistica, restaurant, branch, manager_user, location
):
    ingredient = _ingredient(account_with_logistica, restaurant, branch, manager_user, "Leite")
    today = timezone.localdate()
    for days in (30, 5, 60):
        StockLot.objects.create(
            account=account_with_logistica, restaurant=restaurant, branch=branch, ingredient=ingredient,
            location=location, code=f"LEI-{days}", entered_at=today, expires_at=today + timedelta(days=days),
            initial_quantity=Decimal("2"), quantity=Decimal("2"),
            created_by=manager_user, updated_by=manager_user,
        )

    row = _positions(api_client.get("/api/v1/stock/positions/"))["Leite"]

    assert row["lot_count"] == 3
    assert row["next_expiry"] == str(today + timedelta(days=5))
    assert row["expired"] is False
