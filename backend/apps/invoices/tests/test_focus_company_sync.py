from unittest.mock import Mock, patch

import pytest

from apps.invoices.focus import FocusNfeApiError, FocusNfeCompanyClient, build_focus_company_payload, sync_focus_company
from apps.invoices.models import FiscalConfig

pytestmark = pytest.mark.django_db


class FakeCompanyClient:
    def __init__(self, *, listed=None, created=None, updated=None, dry_run=False):
        self.listed = listed if listed is not None else []
        self.created = created or {}
        self.updated = updated or {}
        self.dry_run = dry_run
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


class DuplicateOnCreateClient(FakeCompanyClient):
    def __init__(self, *, visible_after_conflict=True):
        super().__init__(updated={"id": 789, "token_homologacao": "hom-token"})
        self.visible_after_conflict = visible_after_conflict
        self.list_count = 0

    def list(self, *, cnpj=None, offset=0):
        self.calls.append(("list", cnpj))
        self.list_count += 1
        if self.list_count == 1 or not self.visible_after_conflict:
            return []
        return {"data": {"empresas": [{"id": 789}]}}

    def create(self, payload):
        self.calls.append(("create", payload))
        raise FocusNfeApiError(
            "A Focus NFe informou que a empresa ja esta cadastrada.",
            error_code="focus_conflict",
            upstream_status=422,
        )


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


def test_sync_recovers_duplicate_create_by_listing_company_again(account, restaurant, branch):
    config = make_config(account, restaurant, branch)
    client = DuplicateOnCreateClient()

    result = sync_focus_company(config, client=client)

    config.refresh_from_db()
    assert result.synced is True
    assert result.operation == "recovered"
    assert config.focus_company_id == "789"
    assert config.focus_token_homologation == "hom-token"
    assert [call[0] for call in client.calls] == ["list", "create", "list", "update", "webhook"]


def test_sync_explains_when_duplicate_company_is_not_visible_to_master_token(account, restaurant, branch):
    config = make_config(account, restaurant, branch)
    client = DuplicateOnCreateClient(visible_after_conflict=False)

    with pytest.raises(FocusNfeApiError, match="mesma conta Focus") as error:
        sync_focus_company(config, client=client)

    config.refresh_from_db()
    assert error.value.error_code == "focus_company_conflict_unresolved"
    assert config.focus_sync_status == FiscalConfig.FOCUS_SYNC_ERROR


def test_dry_run_validates_without_marking_company_as_created(account, restaurant, branch):
    config = make_config(account, restaurant, branch)
    client = FakeCompanyClient(created={"id": 999}, dry_run=True)

    result = sync_focus_company(config, client=client)

    config.refresh_from_db()
    assert result.synced is False
    assert result.dry_run is True
    assert config.focus_company_id == ""
    assert config.focus_sync_status == FiscalConfig.FOCUS_SYNC_NOT_CONFIGURED
    assert [call[0] for call in client.calls] == ["list", "create"]


def test_sync_does_not_claim_success_when_focus_does_not_return_or_list_company(account, restaurant, branch):
    config = make_config(account, restaurant, branch)
    client = FakeCompanyClient(created={"mensagem": "ok"})

    with pytest.raises(FocusNfeApiError, match="nao apareceu na consulta por CNPJ") as error:
        sync_focus_company(config, client=client)

    config.refresh_from_db()
    assert error.value.error_code == "focus_company_not_persisted"
    assert config.focus_sync_status == FiscalConfig.FOCUS_SYNC_ERROR
    assert [call[0] for call in client.calls] == ["list", "create", "list"]


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


@patch("requests.request")
def test_company_client_returns_actionable_message_when_master_token_is_rejected(mock_request, account):
    account_config = account.focus_nfe_config
    account_config.master_token = "token-incorreto"
    account_config.production_url = "https://api.focusnfe.com.br"
    account_config.save()
    response = mock_request.return_value
    response.status_code = 401
    response.content = b'{"mensagem":"Nao autorizado"}'
    response.json.return_value = {"mensagem": "Nao autorizado"}

    with pytest.raises(FocusNfeApiError, match="Token Principal de Producao") as error:
        FocusNfeCompanyClient(account_config=account_config).list(cnpj="11222333000181")

    assert error.value.error_code == "focus_auth_error"
    assert error.value.upstream_status == 401


@patch("requests.request")
def test_company_client_classifies_duplicate_response_as_conflict(mock_request, account):
    account_config = account.focus_nfe_config
    account_config.master_token = "master-token"
    account_config.production_url = "https://api.focusnfe.com.br"
    account_config.save()
    response = mock_request.return_value
    response.status_code = 422
    response.content = b'{"mensagem":"Ja existe um registro com estes dados (valor duplicado)."}'
    response.json.return_value = {"mensagem": "Ja existe um registro com estes dados (valor duplicado)."}

    with pytest.raises(FocusNfeApiError) as error:
        FocusNfeCompanyClient(account_config=account_config).create({"cnpj": "11222333000181"})

    assert error.value.error_code == "focus_conflict"
    assert error.value.upstream_status == 422


@patch("requests.request")
def test_manual_sync_endpoint_reports_dry_run_without_claiming_creation(
    mock_request, admin_client, account, restaurant, branch
):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    account_config = account.focus_nfe_config
    account_config.master_token = "master-token"
    account_config.production_url = "https://api.focusnfe.com.br"
    account_config.company_dry_run = True
    account_config.save()
    config = make_config(account, restaurant, branch)

    list_response = Mock(status_code=200, content=b"[]")
    list_response.json.return_value = []
    create_response = Mock(status_code=200, content=b'{"id":999}')
    create_response.json.return_value = {"id": 999}
    mock_request.side_effect = [list_response, create_response]

    response = admin_client.post(f"/api/v1/fiscal/config/{config.pk}/focus-sync/", {}, format="json")

    assert response.status_code == 200, response.data
    assert response.data["synced"] is False
    assert response.data["dry_run"] is True
    assert "nao criou nem alterou" in response.data["message"]
    assert response.data["config"]["focus_company_id"] == ""


@patch("requests.request")
def test_manual_sync_endpoint_returns_structured_focus_error(
    mock_request, admin_client, account, restaurant, branch
):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    account_config = account.focus_nfe_config
    account_config.master_token = "token-incorreto"
    account_config.production_url = "https://api.focusnfe.com.br"
    account_config.company_dry_run = False
    account_config.save()
    config = make_config(account, restaurant, branch)

    focus_response = Mock(status_code=401, content=b'{"mensagem":"Nao autorizado"}')
    focus_response.json.return_value = {"mensagem": "Nao autorizado"}
    mock_request.return_value = focus_response

    response = admin_client.post(f"/api/v1/fiscal/config/{config.pk}/focus-sync/", {}, format="json")

    assert response.status_code == 400, response.data
    assert response.data["synced"] is False
    assert response.data["error"]["code"] == "focus_auth_error"
    assert response.data["focus_status_code"] == 401
    assert "Token Principal de Producao" in response.data["message"]


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
