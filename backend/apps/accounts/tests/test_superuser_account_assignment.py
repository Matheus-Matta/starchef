"""Superusuário precisa poder agir em OUTRA conta via o header X-Account-ID.

Sem enviar esse header, um superusuário criando um usuário sempre acabava
com o usuário caindo na própria conta dele (TenantMiddleware.resolve_account
cai em profile.account quando não há X-Account-ID) — mesmo mecanismo já
suportado pelo TenantAdminMixin do Django Admin, só que o frontend nunca
mandava esse header em request nenhum.
"""
import uuid

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from django.contrib.auth import get_user_model

from apps.accounts.models import Account, UserProfile

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def other_account(db):
    return Account.objects.create(
        name="Outra Conta",
        slug=f"outra-{uuid.uuid4().hex[:8]}",
        status=Account.STATUS_ACTIVE,
        is_active=True,
    )


def _superuser_client(account):
    """APIClient autenticado como superusuário com perfil na própria conta dev."""
    user = User.objects.create_superuser(
        username=f"root-{uuid.uuid4().hex[:6]}", password="x", email=f"{uuid.uuid4().hex[:6]}@test.com"
    )
    UserProfile.objects.create(account=account, user=user, profile_type=UserProfile.PROFILE_ADMIN)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    return client


def test_superuser_creates_user_for_target_account_via_header(account, other_account):
    client = _superuser_client(account)  # perfil do superuser é da conta "account"

    payload = {
        "username": f"novo-{uuid.uuid4().hex[:6]}",
        "email": f"novo-{uuid.uuid4().hex[:6]}@test.com",
        "password": "senha12345",
        "profile": {"profile_type": UserProfile.PROFILE_WAITER},
    }
    resp = client.post("/api/v1/users/", payload, format="json", HTTP_X_ACCOUNT_ID=str(other_account.id))

    assert resp.status_code == 201, resp.data
    created = User.objects.get(username=payload["username"])
    assert created.profile.account_id == other_account.id
    assert created.profile.account_id != account.id


def test_superuser_without_header_falls_back_to_own_account(account, other_account):
    client = _superuser_client(account)

    payload = {
        "username": f"novo-{uuid.uuid4().hex[:6]}",
        "email": f"novo-{uuid.uuid4().hex[:6]}@test.com",
        "password": "senha12345",
        "profile": {"profile_type": UserProfile.PROFILE_WAITER},
    }
    resp = client.post("/api/v1/users/", payload, format="json")

    assert resp.status_code == 201, resp.data
    created = User.objects.get(username=payload["username"])
    assert created.profile.account_id == account.id


def test_non_superuser_header_is_ignored(account, restaurant, branch, other_account):
    user = User.objects.create_user(username=f"adm-{uuid.uuid4().hex[:6]}", password="x")
    UserProfile.objects.create(
        account=account, user=user, profile_type=UserProfile.PROFILE_ADMIN, restaurant=restaurant, branch=branch
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")

    payload = {
        "username": f"novo-{uuid.uuid4().hex[:6]}",
        "password": "senha12345",
        "profile": {"profile_type": UserProfile.PROFILE_WAITER},
    }
    resp = client.post("/api/v1/users/", payload, format="json", HTTP_X_ACCOUNT_ID=str(other_account.id))

    assert resp.status_code == 201, resp.data
    created = User.objects.get(username=payload["username"])
    assert created.profile.account_id == account.id
