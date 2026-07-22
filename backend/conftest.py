"""
Fixtures compartilhadas de teste (multi-tenant + API autenticada).

Constrói o grafo mínimo — conta ativa, restaurante, filial, usuário com perfil —
e devolve um APIClient já autenticado por JWT, exercitando a stack real
(TenantMiddleware resolve a conta a partir de `user.profile.account`).
"""
import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Account, UserProfile
from apps.restaurants.models import Branch, Restaurant

User = get_user_model()


@pytest.fixture
def account(db):
    return Account.objects.create(
        name="Conta Teste",
        slug=f"conta-{uuid.uuid4().hex[:8]}",
        status=Account.STATUS_ACTIVE,
        is_active=True,
    )


@pytest.fixture
def restaurant(account):
    return Restaurant.objects.create(
        account=account,
        legal_name="Restaurante Teste LTDA",
        trade_name="Restaurante Teste",
        cnpj=f"{uuid.uuid4().int % 10**14:014d}",
    )


@pytest.fixture
def branch(account, restaurant):
    return Branch.objects.create(account=account, restaurant=restaurant, name="Matriz")


@pytest.fixture
def manager_user(account, restaurant, branch):
    """Usuário não-admin com escopo de restaurante/filial (perfil de gerente)."""
    user = User.objects.create_user(username="gerente", password="x", email="gerente@test.com")
    UserProfile.objects.create(
        account=account,
        user=user,
        profile_type=UserProfile.PROFILE_MANAGER,
        restaurant=restaurant,
        branch=branch,
    )
    return user


@pytest.fixture
def admin_user(account, restaurant, branch):
    """Usuário admin do tenant (enxerga a conta inteira)."""
    user = User.objects.create_user(username="admin-tenant", password="x", email="admin@test.com")
    UserProfile.objects.create(
        account=account,
        user=user,
        profile_type=UserProfile.PROFILE_ADMIN,
        restaurant=restaurant,
        branch=branch,
    )
    return user


def _authenticated_client(user):
    client = APIClient()
    access = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


@pytest.fixture
def api_client(manager_user):
    """APIClient autenticado como gerente (escopo de restaurante/filial)."""
    return _authenticated_client(manager_user)


@pytest.fixture
def admin_client(admin_user):
    """APIClient autenticado como admin do tenant."""
    return _authenticated_client(admin_user)
