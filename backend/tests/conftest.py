from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import Account, UserProfile
from apps.core.tenant import tenant_context
from apps.menu.models import Ingredient, Product, ProductCategory, Recipe, RecipeItem
from apps.payments.models import PaymentMethod
from apps.restaurants.models import Branch, Command, Restaurant, Table, TableSector

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def account(db):
    return Account.objects.create(name="StarChef Conta", slug="starchef")


@pytest.fixture(autouse=True)
def active_account_context(account):
    with tenant_context(account):
        yield


@pytest.fixture
def restaurant(account):
    return Restaurant.objects.create(
        account=account,
        legal_name="StarChef Restaurante LTDA",
        trade_name="StarChef",
        cnpj="00.000.000/0001-00",
    )


@pytest.fixture
def branch(account, restaurant):
    return Branch.objects.create(
        account=account,
        restaurant=restaurant,
        name="Matriz",
        address="Rua Principal, 100",
        city="Sao Paulo",
        state="SP",
        require_open_cash_register=True,
    )


@pytest.fixture
def manager_user(db, account, restaurant, branch):
    user = User.objects.create_user("manager", email="manager@starchef.test", password="secret123")
    UserProfile.objects.create(
        account=account,
        user=user,
        profile_type=UserProfile.PROFILE_MANAGER,
        restaurant=restaurant,
        branch=branch,
    )
    return user


@pytest.fixture
def waiter_user(db, account, restaurant, branch):
    user = User.objects.create_user("waiter", email="waiter@starchef.test", password="secret123")
    UserProfile.objects.create(
        account=account,
        user=user,
        profile_type=UserProfile.PROFILE_WAITER,
        restaurant=restaurant,
        branch=branch,
    )
    return user


@pytest.fixture
def table(account, restaurant, branch):
    sector = TableSector.objects.create(account=account, restaurant=restaurant, branch=branch, name="Salao")
    return Table.objects.create(account=account, restaurant=restaurant, branch=branch, sector=sector, number="1", capacity=4)


@pytest.fixture
def command(account, restaurant, branch):
    # number/code auto-atribuídos pelo Command.save().
    return Command.objects.create(account=account, restaurant=restaurant, branch=branch)


@pytest.fixture
def category(account, restaurant, branch):
    return ProductCategory.objects.create(account=account, restaurant=restaurant, branch=branch, name="Lanches")


@pytest.fixture
def product(account, restaurant, branch, category):
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


@pytest.fixture
def product_with_recipe(product, account, restaurant, branch, manager_user):
    bread = Ingredient.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Pao",
        unit=Ingredient.UNIT_UNIT,
        average_cost=Decimal("1.20"),
    )
    recipe = Recipe.objects.create(account=account, restaurant=restaurant, branch=branch, product=product)
    RecipeItem.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        recipe=recipe,
        ingredient=bread,
        quantity=Decimal("1"),
        unit=Ingredient.UNIT_UNIT,
        ingredient_cost=Decimal("1.20"),
        total_cost=Decimal("1.20"),
    )
    return product


@pytest.fixture
def payment_method(account, restaurant, branch):
    return PaymentMethod.objects.get_or_create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="PIX",
        defaults={"method_type": PaymentMethod.TYPE_PIX},
    )[0]
