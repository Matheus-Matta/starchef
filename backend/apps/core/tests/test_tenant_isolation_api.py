"""Isolamento por conta na API — inclusive para superusuário.

Duas regressões cobertas aqui:

1. **Escopo global vazando no frontend**: superusuário sem `X-Account-ID` fazia
   `request.account = None` e o `TenantQuerySetMixin` devolvia o queryset SEM
   filtro de conta, ou seja, dados de todas as contas na API que alimenta o
   frontend. Ver tudo é papel do /admin (isento do TenantMiddleware).
2. **Sessão do /admin contaminando a API**: o AuthenticationMiddleware deixa
   `request.user` preenchido pelo cookie `sessionid`; o TenantMiddleware
   aceitava esse usuário e resolvia a conta por ele, então logar no /admin
   mudava o que o app via. A identidade da API vem sempre do JWT.
"""
import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Account, UserProfile
from apps.accounts.role_catalog import ensure_system_roles
from apps.menu.models import Product
from apps.restaurants.models import Branch, Restaurant

pytestmark = pytest.mark.django_db

User = get_user_model()


def _product(account, restaurant, branch, name):
    return Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name=name,
        internal_code=f"C-{uuid.uuid4().hex[:6]}",
        sale_price=10,
    )


@pytest.fixture
def other_account(db):
    account = Account.objects.create(
        name="Conta Vizinha",
        slug=f"vizinha-{uuid.uuid4().hex[:8]}",
        status=Account.STATUS_ACTIVE,
        is_active=True,
    )
    restaurant = Restaurant.objects.create(
        account=account,
        legal_name="Vizinha LTDA",
        trade_name="Vizinha",
        cnpj=f"{uuid.uuid4().int % 10**14:014d}",
    )
    branch = Branch.objects.create(account=account, restaurant=restaurant, name="Matriz")
    _product(account, restaurant, branch, "Produto da outra conta")
    return account


def _client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.fixture
def superuser_with_profile(account, restaurant, branch):
    user = User.objects.create_superuser(
        username=f"root-{uuid.uuid4().hex[:6]}", password="x", email=f"{uuid.uuid4().hex[:6]}@test.com"
    )
    UserProfile.objects.create(
        account=account, user=user, role=ensure_system_roles(account)["admin"], restaurant=restaurant, branch=branch
    )
    return user


@pytest.fixture
def superuser_without_profile(db):
    return User.objects.create_superuser(
        username=f"root-{uuid.uuid4().hex[:6]}", password="x", email=f"{uuid.uuid4().hex[:6]}@test.com"
    )


def test_superuser_com_perfil_ve_so_a_propria_conta(
    superuser_with_profile, account, restaurant, branch, other_account
):
    _product(account, restaurant, branch, "Produto da minha conta")

    resp = _client_for(superuser_with_profile).get("/api/v1/menu/products/")

    assert resp.status_code == 200, resp.data
    nomes = [row["name"] for row in resp.data["results"]]
    assert nomes == ["Produto da minha conta"]


def test_superuser_troca_de_conta_pelo_header(superuser_with_profile, account, restaurant, branch, other_account):
    _product(account, restaurant, branch, "Produto da minha conta")

    resp = _client_for(superuser_with_profile).get(
        "/api/v1/menu/products/", HTTP_X_ACCOUNT_ID=str(other_account.id)
    )

    assert resp.status_code == 200, resp.data
    nomes = [row["name"] for row in resp.data["results"]]
    assert nomes == ["Produto da outra conta"]


def test_superuser_sem_conta_vinculada_e_barrado_com_mensagem_clara(superuser_without_profile, other_account):
    """Sem conta vinculada não há app: o superusuário opera como admin da conta
    dele, e a visão de todas as contas é o /admin."""
    resp = _client_for(superuser_without_profile).get("/api/v1/menu/products/")

    assert resp.status_code == 403
    assert "não está vinculado a nenhuma conta" in resp.json()["detail"]


def test_superuser_sem_conta_nao_lista_usuarios_de_outras_contas(
    superuser_without_profile, account, admin_user, other_account
):
    resp = _client_for(superuser_without_profile).get("/api/v1/users/")

    assert resp.status_code == 403


def test_header_de_conta_inexistente_devolve_404_explicito(superuser_with_profile):
    resp = _client_for(superuser_with_profile).get(
        "/api/v1/menu/products/", HTTP_X_ACCOUNT_ID=str(uuid.uuid4())
    )

    assert resp.status_code == 404
    assert "X-Account-ID" in resp.json()["detail"]


def test_login_recusa_superusuario_sem_conta_vinculada(superuser_without_profile):
    superuser_without_profile.set_password("senha12345")
    superuser_without_profile.save(update_fields=["password"])

    resp = APIClient().post(
        "/api/v1/auth/login/",
        {"username": superuser_without_profile.username, "password": "senha12345"},
        format="json",
    )

    assert resp.status_code == 401
    assert "conta vinculada" in str(resp.json()["error"]["message"])


def test_login_aceita_superusuario_com_conta(superuser_with_profile, account):
    superuser_with_profile.set_password("senha12345")
    superuser_with_profile.save(update_fields=["password"])

    resp = APIClient().post(
        "/api/v1/auth/login/",
        {"username": superuser_with_profile.username, "password": "senha12345"},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    assert resp.data["user"]["account_id"] == str(account.id)


def test_sessao_do_admin_nao_autentica_a_api(client, superuser_with_profile, account, restaurant, branch):
    """Logado no /admin, uma chamada de API sem JWT continua 401 — a sessão não
    vira identidade de API (era isso que fazia o /admin 'vazar' para o app)."""
    client.force_login(superuser_with_profile)

    resp = client.get("/api/v1/menu/products/")

    assert resp.status_code == 401


def test_sessao_do_admin_nao_sobrepoe_o_jwt_do_app(
    superuser_with_profile, manager_user, account, restaurant, branch, other_account
):
    """Com sessão de superusuário E JWT de outro usuário no mesmo request, quem
    manda é o JWT: a conta resolvida é a do dono do token."""
    _product(account, restaurant, branch, "Produto da minha conta")

    client = APIClient()
    client.force_login(superuser_with_profile)  # cookie de sessão do /admin
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(manager_user).access_token}")

    resp = client.get("/api/v1/menu/products/", HTTP_X_ACCOUNT_ID=str(other_account.id))

    assert resp.status_code == 200, resp.data
    nomes = [row["name"] for row in resp.data["results"]]
    # O header X-Account-ID só vale para superusuário: o gerente segue na conta dele.
    assert nomes == ["Produto da minha conta"]
