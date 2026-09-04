import pytest

from apps.invoices.cosmos import CosmosClient, suggest_fiscal_profile

pytestmark = pytest.mark.django_db


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = b"json"

    def json(self):
        return self._payload


def configure_cosmos(account):
    config = account.cosmos_config
    config.api_token = "cosmos-token"
    config.user_agent = "StarChef Test/1.0"
    config.is_active = True
    config.save()
    return config


def enable_financeiro(account):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])


def test_cosmos_client_selects_best_match_and_maps_fiscal_fields(monkeypatch, account):
    config = configure_cosmos(account)
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return FakeResponse(
            {
                "products": [
                    {
                        "description": "MARMITA TERMICA VAZIA",
                        "gtin": "7890000000001",
                        "ncm": {"code": "39241000", "description": "Artefatos de plastico"},
                    },
                    {
                        "description": "REFEICAO PRONTA CONGELADA",
                        "gtin": "7890000000002",
                        "gpc": {"code": "10006759", "description": "Refeicoes preparadas"},
                        "ncm": {"code": "21069090", "description": "Outras preparacoes alimenticias"},
                        "cest": {"code": "1709900"},
                    },
                ]
            }
        )

    monkeypatch.setattr("apps.invoices.cosmos.requests.get", fake_get)

    suggestion = CosmosClient(config).suggest("refeicao pronta")

    assert suggestion.matched_product == "REFEICAO PRONTA CONGELADA"
    assert suggestion.ncm == "21069090"
    assert suggestion.cest == "1709900"
    assert suggestion.gpc_description == "Refeicoes preparadas"
    assert captured["headers"]["X-Cosmos-Token"] == "cosmos-token"
    assert captured["headers"]["User-Agent"] == "StarChef Test/1.0"


def test_suggestion_is_cached_per_account_and_configuration(monkeypatch, account):
    configure_cosmos(account)
    calls = 0

    def fake_get(_url, **_kwargs):
        nonlocal calls
        calls += 1
        return FakeResponse(
            {"products": [{"description": "CAFE CACHE UNICO", "ncm": {"code": "09012100"}}]}
        )

    monkeypatch.setattr("apps.invoices.cosmos.requests.get", fake_get)

    first = suggest_fiscal_profile(account, "cafe cache unico")
    second = suggest_fiscal_profile(account, "cafe cache unico")

    assert first.cached is False
    assert second.cached is True
    assert calls == 1


def test_fiscal_profile_cosmos_actions_return_status_and_suggestion(monkeypatch, admin_client, account):
    enable_financeiro(account)
    configure_cosmos(account)
    monkeypatch.setattr(
        "apps.invoices.cosmos.requests.get",
        lambda *_args, **_kwargs: FakeResponse(
            {"products": [{"description": "SUCO DE LARANJA", "ncm": {"code": "20091200"}}]}
        ),
    )

    status_response = admin_client.get("/api/v1/fiscal/profiles/cosmos-status/")
    suggestion_response = admin_client.get(
        "/api/v1/fiscal/profiles/cosmos-suggest/",
        {"query": "suco de laranja"},
    )

    assert status_response.status_code == 200, status_response.data
    assert status_response.data == {"active": True, "configured": True, "ready": True}
    assert suggestion_response.status_code == 200, suggestion_response.data
    assert suggestion_response.data["fields"]["ncm"] == "20091200"
    assert "api_token" not in suggestion_response.data


def test_suggestion_requires_active_account_configuration(admin_client, account):
    enable_financeiro(account)

    response = admin_client.get(
        "/api/v1/fiscal/profiles/cosmos-suggest/",
        {"query": "refeicao pronta"},
    )

    assert response.status_code == 409
    assert response.data["error"]["code"] == "cosmos_not_configured"
