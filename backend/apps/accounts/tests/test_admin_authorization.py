import uuid

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Account, Permission, UserProfile
from apps.accounts.role_catalog import ensure_system_roles
from apps.core.models import AuditLog

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


def test_usuario_sem_permissao_nao_autoriza_cancelamento(api_client, account, restaurant, branch):
    # Garçom: o único cargo fixo cujo catálogo NÃO inclui "orders.cancel"
    # (waiter/cashier ficam abaixo de manager na hierarquia — ver role_catalog.py).
    waiter = User.objects.create_user(username="garcom-sem-permissao", password="x")
    UserProfile.objects.create(
        account=account, user=waiter, role=ensure_system_roles(account)["waiter"], restaurant=restaurant, branch=branch
    )

    response = api_client.post(
        "/api/v1/auth/authorize-admin/",
        {
            "username": waiter.username,
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
        role=ensure_system_roles(other_account)["admin"],
    )

    response = api_client.post(
        "/api/v1/auth/authorize-admin/",
        {"username": other_admin.username, "password": "x"},
        format="json",
    )

    assert response.status_code == 403


def test_a_autorizacao_concedida_fica_na_auditoria(api_client, admin_user):
    """Quem pediu, quem liberou e para quê.

    E a pergunta que a auditoria existe para responder justamente no caso em
    que ela importa: um operador sem a permissao fez algo que a permissao dele
    nao permite, porque alguem a emprestou para aquela operacao.
    """
    response = api_client.post(
        "/api/v1/auth/authorize-admin/",
        {
            "username": admin_user.username,
            "password": "x",
            "permission": "orders.cancel",
            "reason": "Cliente desistiu do pedido",
        },
        format="json",
        HTTP_X_TERMINAL_ID="balcao-02",
    )

    assert response.status_code == 200
    registro = AuditLog.all_objects.filter(metadata__event="authorization_granted").latest("created_at")
    assert registro.metadata["permission"] == "orders.cancel"
    assert registro.metadata["authorized_by_username"] == admin_user.username
    assert registro.metadata["requested_by_username"]
    assert registro.metadata["terminal"] == "balcao-02"
    assert registro.reason == "Cliente desistiu do pedido"


def test_permissao_fora_do_catalogo_nao_pode_ser_emprestada(api_client, admin_user):
    """A autorizacao empresta poder para UMA operacao conhecida.

    Aceitar qualquer codigo transformaria a senha do administrador numa
    chave-mestra para qualquer coisa que alguem pensasse em pedir daqui.
    """
    response = api_client.post(
        "/api/v1/auth/authorize-admin/",
        {
            "username": admin_user.username,
            "password": "x",
            "permission": "users.delete",
        },
        format="json",
    )

    assert response.status_code == 400


def test_o_catalogo_cobre_as_operacoes_da_sprint(api_client, admin_user):
    for permissao in ("orders.cancel", "orders.discount", "cash.manage", "settings.manage"):
        response = api_client.post(
            "/api/v1/auth/authorize-admin/",
            {"username": admin_user.username, "password": "x", "permission": permissao},
            format="json",
        )
        assert response.status_code == 200, permissao
