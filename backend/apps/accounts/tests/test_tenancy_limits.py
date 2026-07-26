"""Limites de tenancy (usuários/restaurantes) aplicados no cadastro via API."""
import uuid

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import UserProfile

pytestmark = pytest.mark.django_db


def _admin_client(account, restaurant, branch):
    """APIClient autenticado como admin do tenant (não superuser)."""
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    User = get_user_model()
    user = User.objects.create_user(username=f"adm-{uuid.uuid4().hex[:6]}", password="x")
    UserProfile.objects.create(
        account=account, user=user, profile_type=UserProfile.PROFILE_ADMIN, restaurant=restaurant, branch=branch
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    return client


# ── Restaurantes ────────────────────────────────────────────────────────────
def test_restaurant_limit_blocks_creation_with_custom_message(account, restaurant, branch):
    # A conta já tem 1 restaurante (fixture) e o limite é 1 → o próximo é bloqueado.
    account.max_restaurants = 1
    account.save(update_fields=["max_restaurants"])
    client = _admin_client(account, restaurant, branch)

    resp = client.post("/api/v1/restaurants/", {"trade_name": "Novo", "legal_name": "Novo LTDA"}, format="json")

    assert resp.status_code == 409, resp.data
    assert resp.data["error"]["code"] == "limit_reached"
    assert "Limite de restaurantes atingido" in resp.data["error"]["message"]["detail"]


def test_restaurant_limit_unlimited_when_zero(account, restaurant, branch):
    account.max_restaurants = 0  # 0 = ilimitado
    account.save(update_fields=["max_restaurants"])
    client = _admin_client(account, restaurant, branch)

    resp = client.post("/api/v1/restaurants/", {"trade_name": "Outro", "legal_name": "Outro LTDA"}, format="json")

    assert resp.status_code == 201, resp.data


def test_restaurant_limit_allows_up_to_limit(account, restaurant, branch):
    account.max_restaurants = 2  # já há 1; permite mais 1
    account.save(update_fields=["max_restaurants"])
    client = _admin_client(account, restaurant, branch)

    first = client.post("/api/v1/restaurants/", {"trade_name": "R2", "legal_name": "R2 LTDA"}, format="json")
    second = client.post("/api/v1/restaurants/", {"trade_name": "R3", "legal_name": "R3 LTDA"}, format="json")

    assert first.status_code == 201, first.data
    assert second.status_code == 409, second.data


# ── Usuários ────────────────────────────────────────────────────────────────
def test_user_limit_blocks_creation_with_custom_message(account, restaurant, branch):
    # Deixa o limite igual ao total atual de perfis para bloquear o próximo cadastro.
    account.max_users = UserProfile.all_objects.filter(account=account, deleted_at__isnull=True).count()
    account.save(update_fields=["max_users"])
    client = _admin_client(account, restaurant, branch)  # cria +1 perfil (admin)
    account.refresh_from_db()
    account.max_users = UserProfile.all_objects.filter(account=account, deleted_at__isnull=True).count()
    account.save(update_fields=["max_users"])

    payload = {
        "username": f"novo-{uuid.uuid4().hex[:6]}",
        "password": "senha12345",
        "profile": {"profile_type": UserProfile.PROFILE_WAITER},
    }
    resp = client.post("/api/v1/users/", payload, format="json")

    assert resp.status_code == 409, resp.data
    assert resp.data["error"]["code"] == "limit_reached"
    assert "Limite de usuários atingido" in resp.data["error"]["message"]["detail"]


def test_user_limit_unlimited_when_zero(account, restaurant, branch):
    account.max_users = 0
    account.save(update_fields=["max_users"])
    client = _admin_client(account, restaurant, branch)

    payload = {
        "username": f"novo-{uuid.uuid4().hex[:6]}",
        "password": "senha12345",
        "profile": {"profile_type": UserProfile.PROFILE_WAITER},
    }
    resp = client.post("/api/v1/users/", payload, format="json")

    assert resp.status_code == 201, resp.data
