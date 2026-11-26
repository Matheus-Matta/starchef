"""O CSC entregue ao StarChef Desktop: só a quem é da loja, com auditoria."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import UserProfile
from apps.core.models import AuditLog
from apps.invoices.models import FiscalConfig
from apps.restaurants.models import Branch, Restaurant

pytestmark = pytest.mark.django_db


@pytest.fixture
def config(account, restaurant, branch):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    return FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch, provider="acbrlib", environment="2",
        cnpj="11.222.333/0001-81", corporate_name="Loja", series=1, crt="3", csc_id="000001", csc_token="SEGREDO-DO-CSC",
    )


def url(config):
    return f"/api/v1/fiscal/config/{config.pk}/desktop-csc/"


def test_quem_e_da_loja_recebe_o_csc_e_fica_na_auditoria(api_client, config):
    r = api_client.get(url(config))
    assert r.status_code == 200
    assert r.json() == {"csc_id": "000001", "csc_token": "SEGREDO-DO-CSC", "configured": True}
    assert AuditLog.all_objects.filter(metadata__event="desktop_csc_delivered").count() == 1
    # A API comum continua sem devolver o código.
    comum = api_client.get(f"/api/v1/fiscal/config/{config.pk}/").json()
    assert "csc_token" not in comum and comum["csc_token_configured"] is True


def test_de_outra_loja_da_conta_nao_recebe(account, config):
    outra = Restaurant.objects.create(account=account, legal_name="Outra LTDA", trade_name="Outra", cnpj="11222333000262")
    filial = Branch.all_objects.filter(restaurant=outra).first() or Branch.objects.create(account=account, restaurant=outra, name="Filial 2")
    user = get_user_model().objects.create_user(username="caixa-outra", password="x", email="caixa-outra@test.com")
    from conftest import _role_for

    UserProfile.objects.create(account=account, user=user, role=_role_for(account, "manager"), restaurant=outra, branch=filial)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    assert client.get(url(config)).status_code == 404


def test_sem_login_nao_recebe(config):
    assert APIClient().get(url(config)).status_code == 401


def test_nfe_nao_tem_csc(api_client, config):
    FiscalConfig.all_objects.filter(pk=config.pk).update(document_model=FiscalConfig.MODEL_NFE)
    assert api_client.get(url(config)).status_code == 400
