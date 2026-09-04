import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Account, FirstAccessState, Role, UserProfile

User = get_user_model()


@pytest.fixture
def empty_installation(db, account):
    User.objects.all().delete()
    # A conta nasce com os 4 Perfis de Acesso fixos (signal); sem apagá-los
    # primeiro, `Account.account` é protegido (PROTECT) e a conta não some.
    Role.all_objects.all().delete()
    Account.objects.all().delete()
    FirstAccessState.objects.all().delete()


def _payload(token):
    return {
        "account_name": "Conta Principal",
        "account_slug": "conta-principal",
        "account_email": "conta@example.com",
        "first_name": "Admin",
        "last_name": "Principal",
        "username": "superadmin",
        "email": "admin@example.com",
        "password1": "UmaSenha-Forte-2026!",
        "password2": "UmaSenha-Forte-2026!",
        "setup_token": token,
    }


@pytest.mark.django_db
def test_first_access_creates_account_and_superadmin_once(client, settings, empty_installation):
    settings.FIRST_ACCESS_TOKEN = "bootstrap-secret"

    page = client.get("/admin/login/")
    assert page.status_code == 200
    assert "Configuração de primeiro acesso" in page.content.decode()
    assert "csrftoken" in page.cookies

    response = client.post("/admin/login/", _payload("bootstrap-secret"))
    assert response.status_code == 302
    assert response.url == "/admin/login/"

    account = Account.objects.get(slug="conta-principal")
    user = User.objects.get(username="superadmin")
    assert user.is_superuser and user.is_staff
    assert UserProfile.all_objects.get(user=user).account == account
    assert FirstAccessState.objects.count() == 1

    # O mesmo POST agora cai no login normal e nunca recria o bootstrap.
    client.post("/admin/login/", _payload("bootstrap-secret"))
    assert Account.objects.count() == 1
    assert User.objects.count() == 1
    assert FirstAccessState.objects.count() == 1


@pytest.mark.django_db
def test_first_access_rejects_invalid_bootstrap_key(client, settings, empty_installation):
    settings.FIRST_ACCESS_TOKEN = "correct-secret"

    response = client.post("/admin/login/", _payload("wrong-secret"))

    assert response.status_code == 200
    assert "Chave de primeiro acesso inválida" in response.content.decode()
    assert not Account.objects.exists()
    assert not User.objects.exists()
    assert not FirstAccessState.objects.exists()


@pytest.mark.django_db
def test_existing_installation_never_exposes_first_access(client, settings, account):
    settings.FIRST_ACCESS_TOKEN = "bootstrap-secret"

    response = client.get("/admin/login/")

    assert response.status_code == 200
    assert "Configuração de primeiro acesso" not in response.content.decode()
