"""
Sessão do editor do storefront.

O que estes testes protegem, em ordem de gravidade:

1. **Vazamento entre tenants.** O slug do site vem da URL pública
   (`/burger/editor/`), então é entrada do usuário. Quem confere se aquele site
   é dele é o servidor — trocar o slug na barra de endereço não pode abrir o
   editor do vizinho.
2. **Colisão de sessão.** Painel e editor usam cookies de nomes diferentes;
   entrar num não pode derrubar o outro.
3. **Permissão.** Só perfil de e-commerce (ou admin da conta) entra, e só com o
   módulo licenciado.
"""
import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile
from apps.accounts.role_catalog import ensure_system_roles

User = get_user_model()

LOGIN_URL = "/api/v1/storefront/auth/login/"
SESSION_URL = "/api/v1/storefront/auth/session/"
LOGOUT_URL = "/api/v1/storefront/auth/logout/"
REFRESH_URL = "/api/v1/storefront/auth/refresh/"

pytestmark = pytest.mark.django_db


@pytest.fixture
def editor_password(ecommerce_user):
    """As fixtures criam o usuário com senha "x"; o login precisa dela explícita."""
    ecommerce_user.set_password("segredo-123")
    ecommerce_user.save(update_fields=["password"])
    return "segredo-123"


def login(client, username, password, site=None):
    body = {"username": username, "password": password}
    if site is not None:
        body["site"] = site
    return client.post(LOGIN_URL, body, format="json", HTTP_X_AUTH_SCOPE="storefront")


# ── Login ────────────────────────────────────────────────────────────────────


def test_login_do_editor_grava_cookies_proprios(ecommerce_user, editor_password, site):
    client = APIClient()
    response = login(client, ecommerce_user.username, editor_password, site=site.slug)

    assert response.status_code == 200
    # Cookies do EDITOR, não os do painel: é o que permite as duas sessões
    # coexistirem no mesmo navegador.
    assert settings.STOREFRONT_JWT_AUTH_COOKIE in response.cookies
    assert settings.STOREFRONT_JWT_REFRESH_COOKIE in response.cookies
    assert settings.JWT_AUTH_COOKIE not in response.cookies
    assert settings.JWT_AUTH_REFRESH_COOKIE not in response.cookies

    # O access token não pode ser legível por JS — é a defesa contra XSS.
    assert response.cookies[settings.STOREFRONT_JWT_AUTH_COOKIE]["httponly"]
    # A flag de sessão é legível de propósito: o front só a usa para decidir se
    # tenta a sessão antes de mostrar o formulário.
    assert not response.cookies[settings.STOREFRONT_AUTH_SESSION_COOKIE]["httponly"]

    assert response.data["site"]["slug"] == site.slug
    assert response.data["user"]["username"] == ecommerce_user.username


def test_login_com_senha_errada_nao_cria_sessao(ecommerce_user, editor_password):
    response = login(APIClient(), ecommerce_user.username, "senha-errada")

    assert response.status_code == 401
    assert settings.STOREFRONT_JWT_AUTH_COOKIE not in response.cookies


def test_login_recusa_site_de_outro_restaurante(ecommerce_user, editor_password, other_account_setup):
    """O caso que motiva o endpoint: credencial boa, site alheio."""
    response = login(
        APIClient(), ecommerce_user.username, editor_password, site=other_account_setup["site"].slug
    )

    assert response.status_code == 403
    # E nenhuma sessão é criada — não adianta insistir depois com outro slug.
    assert settings.STOREFRONT_JWT_AUTH_COOKIE not in response.cookies


def test_login_recusa_perfil_sem_permissao_de_site(waiter_user, site):
    waiter_user.set_password("segredo-123")
    waiter_user.save(update_fields=["password"])

    response = login(APIClient(), waiter_user.username, "segredo-123", site=site.slug)

    assert response.status_code == 403
    assert settings.STOREFRONT_JWT_AUTH_COOKIE not in response.cookies


def test_login_recusa_conta_sem_o_modulo_de_ecommerce(ecommerce_user, editor_password, ecommerce_account, site):
    ecommerce_account.enabled_modules = []
    ecommerce_account.save(update_fields=["enabled_modules", "updated_at"])

    response = login(APIClient(), ecommerce_user.username, editor_password, site=site.slug)

    assert response.status_code == 403
    # O envelope de erro da API é `{"error": {"code", "message"}}`; a mensagem
    # em si pode vir como string ou como o dict `{"detail": ...}` do DRF.
    assert "e-commerce" in str(response.data["error"]["message"]).lower()


# ── Sessão ───────────────────────────────────────────────────────────────────


def test_sessao_sem_cookie_e_401(site):
    response = APIClient().get(f"{SESSION_URL}?site={site.slug}", HTTP_X_AUTH_SCOPE="storefront")
    assert response.status_code == 401


def test_sessao_confirma_o_site_do_proprio_restaurante(ecommerce_user, editor_password, site):
    client = APIClient()
    login(client, ecommerce_user.username, editor_password)

    response = client.get(f"{SESSION_URL}?site={site.slug}", HTTP_X_AUTH_SCOPE="storefront")

    assert response.status_code == 200
    assert response.data["site"]["id"] == str(site.id)
    assert [row["slug"] for row in response.data["sites"]] == [site.slug]


def test_sessao_nega_site_de_outro_tenant(ecommerce_user, editor_password, site, other_account_setup):
    """Guarda da rota `/{slug}/editor/`: o slug é entrada, não credencial."""
    client = APIClient()
    login(client, ecommerce_user.username, editor_password)

    response = client.get(
        f"{SESSION_URL}?site={other_account_setup['site'].slug}", HTTP_X_AUTH_SCOPE="storefront"
    )

    assert response.status_code == 403


def test_sessao_nao_vaza_sites_de_outra_conta(ecommerce_user, editor_password, site, other_account_setup):
    client = APIClient()
    login(client, ecommerce_user.username, editor_password)

    response = client.get(SESSION_URL, HTTP_X_AUTH_SCOPE="storefront")

    slugs = {row["slug"] for row in response.data["sites"]}
    assert slugs == {site.slug}
    assert other_account_setup["site"].slug not in slugs
    # Nem o nome da conta rival aparece em lugar nenhum da resposta.
    assert "Conta Rival" not in str(response.data)
    assert other_account_setup["site"].name not in str(response.data)


def test_sessao_devolve_so_as_permissoes_do_storefront(ecommerce_user, editor_password, site):
    client = APIClient()
    login(client, ecommerce_user.username, editor_password)

    response = client.get(SESSION_URL, HTTP_X_AUTH_SCOPE="storefront")

    assert "storefront.view" in response.data["permissions"]
    # Nada de mapa do que o usuário faz no resto do ERP.
    assert all(code.startswith("storefront.") for code in response.data["permissions"])


def test_usuario_sem_restaurante_e_sem_papel_de_admin_nao_edita_nenhum_site(
    ecommerce_account, branch, site
):
    """`MenuSite.restaurant` é obrigatório: não existe site "da conta inteira"."""
    user = User.objects.create_user(username="solto", password="segredo-123", email="solto@test.com")
    UserProfile.objects.create(
        account=ecommerce_account,
        user=user,
        role=ensure_system_roles(ecommerce_account)["ecommerce"],
        restaurant=None,
        branch=None,
    )

    client = APIClient()
    login(client, "solto", "segredo-123")
    response = client.get(SESSION_URL, HTTP_X_AUTH_SCOPE="storefront")

    assert response.status_code == 200
    assert response.data["sites"] == []


# ── Isolamento entre as duas sessões (painel × editor) ───────────────────────


def test_cookie_do_painel_nao_autentica_o_editor(ecommerce_user, editor_password, site):
    """Sem o cookie `sf_*`, o editor é anônimo — mesmo com o painel logado."""
    client = APIClient()
    # Simula a sessão do painel no mesmo navegador.
    panel = APIClient()
    panel.post(
        "/api/v1/auth/login/",
        {"username": ecommerce_user.username, "password": editor_password},
        format="json",
    )
    panel_cookie = panel.cookies.get(settings.JWT_AUTH_COOKIE)
    assert panel_cookie is not None

    client.cookies[settings.JWT_AUTH_COOKIE] = panel_cookie.value
    response = client.get(SESSION_URL, HTTP_X_AUTH_SCOPE="storefront")

    assert response.status_code == 401


def test_logout_do_editor_nao_derruba_a_sessao_do_painel(ecommerce_user, editor_password, site):
    client = APIClient()
    login(client, ecommerce_user.username, editor_password)
    client.cookies[settings.JWT_AUTH_COOKIE] = "token-do-painel-intocado"

    response = client.post(LOGOUT_URL, HTTP_X_AUTH_SCOPE="storefront")

    assert response.status_code == 204
    # Os `sf_*` são apagados (valor vazio no Set-Cookie)...
    assert response.cookies[settings.STOREFRONT_JWT_AUTH_COOKIE].value == ""
    # ...e os do painel nem são tocados.
    assert settings.JWT_AUTH_COOKIE not in response.cookies


def test_refresh_do_editor_usa_o_cookie_proprio(ecommerce_user, editor_password, site):
    client = APIClient()
    login(client, ecommerce_user.username, editor_password)

    response = client.post(REFRESH_URL, HTTP_X_AUTH_SCOPE="storefront")

    assert response.status_code == 200
    assert response.cookies[settings.STOREFRONT_JWT_AUTH_COOKIE].value


def test_refresh_sem_cookie_do_editor_e_401():
    response = APIClient().post(REFRESH_URL, HTTP_X_AUTH_SCOPE="storefront")
    assert response.status_code == 401


# ── Slug do site ─────────────────────────────────────────────────────────────


def test_slug_do_site_e_unico_na_plataforma_inteira(site, other_account_setup):
    """É o que permite a URL `/<slug>/` identificar o restaurante sozinha."""
    from django.db import IntegrityError, transaction

    from apps.storefront.models import MenuSite

    with pytest.raises(IntegrityError), transaction.atomic():
        MenuSite.all_objects.create(
            account=other_account_setup["account"],
            restaurant=other_account_setup["restaurant"],
            name="Clone",
            slug=site.slug,
        )

    assert uuid.UUID(str(site.id))
