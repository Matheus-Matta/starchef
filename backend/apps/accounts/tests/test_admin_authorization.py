import uuid

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Account, Permission, UserProfile

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_admin_da_mesma_conta_autoriza_por_usuario(api_client, admin_user):
    response = api_client.post(
        "/api/v1/auth/authorize-admin/",
        {"username": admin_user.username, "password": "x"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["authorized"] is True


def test_admin_da_mesma_conta_autoriza_por_email(api_client, admin_user):
    response = api_client.post(
        "/api/v1/auth/authorize-admin/",
        {"username": admin_user.email, "password": "x"},
        format="json",
    )

    assert response.status_code == 200


def test_senha_incorreta_nao_autoriza(api_client, admin_user):
    response = api_client.post(
        "/api/v1/auth/authorize-admin/",
        {"username": admin_user.username, "password": "errada"},
        format="json",
    )

    assert response.status_code == 401


def test_gerente_nao_autoriza_como_administrador(api_client, manager_user):
    response = api_client.post(
        "/api/v1/auth/authorize-admin/",
        {"username": manager_user.username, "password": "x"},
        format="json",
    )

    assert response.status_code == 403


def test_usuario_com_permissao_autoriza_cancelamento(api_client, manager_user):
    permission, _ = Permission.objects.get_or_create(
        code="orders.cancel",
        defaults={"name": "Cancelar pedidos"},
    )
    manager_user.profile.specific_permissions.add(permission)

    response = api_client.post(
        "/api/v1/auth/authorize-admin/",
        {
            "username": manager_user.username,
            "password": "x",
            "permission": "orders.cancel",
        },
        format="json",
    )

    assert response.status_code == 200


def test_usuario_sem_permissao_nao_autoriza_cancelamento(api_client, manager_user):
    response = api_client.post(
        "/api/v1/auth/authorize-admin/",
        {
            "username": manager_user.username,
            "password": "x",
            "permission": "orders.cancel",
        },
        format="json",
    )

    assert response.status_code == 403


def test_admin_de_outra_conta_nao_autoriza(api_client):
    other_account = Account.objects.create(
        name="Outra conta",
        slug=f"outra-{uuid.uuid4().hex[:8]}",
        status=Account.STATUS_ACTIVE,
        is_active=True,
    )
    other_admin = User.objects.create_user(
        username="admin-outra-conta",
        password="x",
        email="admin-outra@test.com",
    )
    UserProfile.objects.create(
        account=other_account,
        user=other_admin,
        profile_type=UserProfile.PROFILE_ADMIN,
    )

    response = api_client.post(
        "/api/v1/auth/authorize-admin/",
        {"username": other_admin.username, "password": "x"},
        format="json",
    )

    assert response.status_code == 403
