"""Fixtures do storefront: conta com o módulo E-commerce ligado, site e páginas."""
import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Account, UserProfile
from apps.accounts.role_catalog import ensure_system_roles
from apps.menu.models import Product, ProductCategory
from apps.restaurants.models import Branch, Restaurant
from apps.storefront.models import MenuPage, MenuSite

User = get_user_model()

# Árvore mínima que o editor produz: uma seção com um título dentro.
SIMPLE_PROJECT = {
    "pages": [
        {
            "name": "Home",
            "frames": [
                {
                    "component": {
                        "type": "sf-section",
                        "tagName": "section",
                        "style": {"padding": "40px", "backgroundColor": "#fff"},
                        "components": [
                            {"type": "sf-heading", "tagName": "h1", "content": "Bem-vindo"},
                        ],
                    }
                }
            ],
        }
    ],
    "styles": [{"selectors": [".hero"], "style": {"color": "#111"}}],
    "assets": [],
}


def authenticated_client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.fixture
def ecommerce_account(account):
    """A mesma conta das fixtures globais, com o módulo E-commerce habilitado."""
    account.enabled_modules = ["ecommerce"]
    account.save(update_fields=["enabled_modules", "updated_at"])
    return account


@pytest.fixture
def site(ecommerce_account, restaurant):
    return MenuSite.all_objects.create(
        account=ecommerce_account,
        restaurant=restaurant,
        name="Site do Teste",
        slug=f"site-{uuid.uuid4().hex[:8]}",
        is_active=True,
        theme={"primaryColor": "#E53935"},
    )


@pytest.fixture
def page(site):
    return MenuPage.all_objects.create(
        account=site.account,
        restaurant=site.restaurant,
        site=site,
        title="Home",
        slug="home",
        is_home=True,
        draft_data=SIMPLE_PROJECT,
    )


def _make_user(account, restaurant, branch, role_code, username):
    user = User.objects.create_user(username=username, password="x", email=f"{username}@test.com")
    UserProfile.objects.create(
        account=account,
        user=user,
        role=ensure_system_roles(account)[role_code],
        restaurant=restaurant,
        branch=branch,
    )
    return user


@pytest.fixture
def ecommerce_user(ecommerce_account, restaurant, branch):
    """Perfil de Acesso "E-commerce": o único não-admin que pode editar o site."""
    return _make_user(ecommerce_account, restaurant, branch, "ecommerce", "ecommerce-user")


@pytest.fixture
def ecommerce_client(ecommerce_user):
    return authenticated_client(ecommerce_user)


@pytest.fixture
def waiter_user(ecommerce_account, restaurant, branch):
    return _make_user(ecommerce_account, restaurant, branch, "waiter", "garcom-user")


@pytest.fixture
def other_account_setup(db):
    """Uma segunda conta completa — para os testes de isolamento entre tenants."""
    other_account = Account.objects.create(
        name="Conta Rival",
        slug=f"rival-{uuid.uuid4().hex[:8]}",
        status=Account.STATUS_ACTIVE,
        is_active=True,
        enabled_modules=["ecommerce"],
    )
    other_restaurant = Restaurant.objects.create(
        account=other_account,
        legal_name="Rival LTDA",
        trade_name="Rival",
        cnpj=f"{uuid.uuid4().int % 10**14:014d}",
    )
    other_branch = Branch.objects.create(account=other_account, restaurant=other_restaurant, name="Matriz")
    other_user = _make_user(other_account, other_restaurant, other_branch, "admin", "admin-rival")
    other_site = MenuSite.all_objects.create(
        account=other_account,
        restaurant=other_restaurant,
        name="Site Rival",
        slug=f"rival-{uuid.uuid4().hex[:8]}",
    )
    other_page = MenuPage.all_objects.create(
        account=other_account,
        restaurant=other_restaurant,
        site=other_site,
        title="Home Rival",
        slug="home",
        is_home=True,
        draft_data=SIMPLE_PROJECT,
    )
    return {
        "account": other_account,
        "restaurant": other_restaurant,
        "user": other_user,
        "client": authenticated_client(other_user),
        "site": other_site,
        "page": other_page,
    }


@pytest.fixture
def catalog(ecommerce_account, restaurant, branch):
    """Uma categoria e dois produtos publicáveis (um deles em promoção)."""
    category = ProductCategory.all_objects.create(
        account=ecommerce_account, restaurant=restaurant, branch=branch, name="Pizzas"
    )
    pizza = Product.all_objects.create(
        account=ecommerce_account,
        restaurant=restaurant,
        branch=branch,
        category=category,
        name="Margherita",
        internal_code="PZ-001",
        sale_price="49.90",
    )
    pizza.restaurants.add(restaurant)
    promo = Product.all_objects.create(
        account=ecommerce_account,
        restaurant=restaurant,
        branch=branch,
        category=category,
        name="Calabresa",
        internal_code="PZ-002",
        sale_price="52.00",
        promotional_price="39.90",
    )
    promo.restaurants.add(restaurant)
    return {"category": category, "products": [pizza, promo]}
