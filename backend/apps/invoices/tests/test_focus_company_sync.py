from unittest.mock import patch

import pytest

from apps.invoices.focus import FocusNfeCompanyClient, build_focus_company_payload, sync_focus_company
from apps.invoices.models import FiscalConfig

pytestmark = pytest.mark.django_db


class FakeCompanyClient:
    def __init__(self, *, listed=None, created=None, updated=None):
        self.listed = listed if listed is not None else []
        self.created = created or {}
        self.updated = updated or {}
        self.calls = []

    def list(self, *, cnpj=None, offset=0):
        self.calls.append(("list", cnpj))
        return self.listed

    def create(self, payload):
        self.calls.append(("create", payload))
        return self.created

    def update(self, company_id, payload):
        self.calls.append(("update", str(company_id), payload))
        return self.updated

    def ensure_webhook(self, *, company, cnpj):
        self.calls.append(("webhook", cnpj))


def make_config(account, restaurant, branch, **kwargs):
    defaults = {
        "provider": FiscalConfig.PROVIDER_FOCUS_NFE,
        "cnpj": "11.222.333/0001-81",
        "ie": "123456789",
        "corporate_name": "Restaurante Teste LTDA",
        "trade_name": "Restaurante Teste",
        "address_line": "Rua das Flores, 10",
        "city": "Sao Paulo",
        "uf": "SP",
        "zip_code": "01001-000",
        "environment": FiscalConfig.ENV_HOMOLOGATION,
        "document_model": FiscalConfig.MODEL_NFCE,
        "series": 3,
        "next_number": 12,
    }
    defaults.update(kwargs)
    return FiscalConfig.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        **defaults,
    )


def test_company_payload_maps_restaurant_and_nfce_settings(account, restaurant, branch):
    config = make_config(account, restaurant, branch, csc_id="00001", csc_token="CSC-TESTE")

    payload = build_focus_company_payload(config)

    assert payload["cnpj"] == "11222333000181"
    assert payload["regime_tributario"] == 1
    assert payload["habilita_nfce"] is True
    assert payload["habilita_nfe"] is False
    assert payload["serie_nfce_homologacao"] == "3"
    assert payload["proximo_numero_nfce_homologacao"] == "12"
    assert payload["csc_nfce_homologacao"] == "CSC-TESTE"
    assert payload["id_token_nfce_homologacao"] == 1


def test_sync_creates_company_and_stores_environment_tokens(account, restaurant, branch):
    config = make_config(
        account,
        restaurant,
        branch,
        focus_certificate_base64="BASE64-PFX",
        focus_certificate_password="senha-pfx",
    )
    client = FakeCompanyClient(
        created={
            "id": 123,
            "cnpj": "11222333000181",
            "token_producao": "prod-token",
            "token_homologacao": "hom-token",
        }
    )

    sync_focus_company(config, client=client)

    config.refresh_from_db()
    assert config.focus_company_id == "123"
    assert config.focus_token_production == "prod-token"
    assert config.focus_token_homologation == "hom-token"
    assert config.focus_sync_status == FiscalConfig.FOCUS_SYNC_SYNCED
    assert config.focus_certificate_base64 == ""
    assert config.focus_certificate_password == ""
    create_payload = next(call[1] for call in client.calls if call[0] == "create")
    assert create_payload["arquivo_certificado_base64"] == "BASE64-PFX"
    assert create_payload["senha_certificado"] == "senha-pfx"
    assert "token_producao" not in config.focus_remote_data
    assert [call[0] for call in client.calls] == ["list", "create", "webhook"]


def test_sync_reuses_company_found_by_cnpj(account, restaurant, branch):
    config = make_config(account, restaurant, branch)
    client = FakeCompanyClient(
        listed=[{"id": 456}],
        updated={"id": 456, "token_homologacao": "hom-token"},
    )

    sync_focus_company(config, client=client)

    config.refresh_from_db()
    assert config.focus_company_id == "456"
    assert [call[0] for call in client.calls] == ["list", "update", "webhook"]


@patch("requests.request")
def test_company_client_uses_account_config_instead_of_settings(mock_request, account):
    account_config = account.focus_nfe_config
    account_config.master_token = "master-token"
    account_config.production_url = "https://focus-da-conta.example"
    account_config.company_dry_run = True
    account_config.save()
    response = mock_request.return_value
    response.status_code = 200
    response.content = b"{}"
    response.json.return_value = {"id": 123}

    result = FocusNfeCompanyClient(account_config=account_config).create({"cnpj": "11222333000181"})

    assert result == {"id": 123}
    assert mock_request.call_args.args[:2] == ("POST", "https://focus-da-conta.example/v2/empresas")
    assert mock_request.call_args.kwargs["auth"] == ("master-token", "")
    assert mock_request.call_args.kwargs["params"] == {"dry_run": 1}


@patch("apps.invoices.focus.enqueue_focus_company_sync")
def test_restaurant_registration_creates_focus_config(mock_enqueue, admin_client):
    response = admin_client.post(
        "/api/v1/restaurants/",
        {
            "legal_name": "Nova Empresa LTDA",
            "trade_name": "Nova Empresa",
            "cnpj": "11222333000181",
            "address": "Rua Nova, 10",
            "city": "Sao Paulo",
            "state": "SP",
            "zip_code": "01001000",
            "fiscal_provider": "focus_nfe",
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    config = FiscalConfig.all_objects.get(restaurant_id=response.data["id"])
    assert response.data["fiscal_provider"] == FiscalConfig.PROVIDER_FOCUS_NFE
    assert config.provider == FiscalConfig.PROVIDER_FOCUS_NFE
    assert config.cnpj == "11222333000181"
    mock_enqueue.assert_called_once_with(config)
