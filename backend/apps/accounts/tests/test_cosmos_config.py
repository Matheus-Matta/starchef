import uuid

import pytest

from apps.accounts.models import Account, CosmosConfig

pytestmark = pytest.mark.django_db


def enable_financeiro(account):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])


def test_new_account_receives_inactive_cosmos_config():
    account = Account.objects.create(name="Conta Cosmos", slug=f"cosmos-{uuid.uuid4().hex[:8]}")

    config = CosmosConfig.objects.get(account=account)
    assert config.is_active is False
    assert config.api_token == ""
    assert config.is_ready is False


def test_tenant_admin_can_configure_cosmos_without_reading_token(admin_client, account):
    enable_financeiro(account)

    response = admin_client.patch(
        "/api/v1/integrations/cosmos/config/",
        {
            "api_token": "token-da-conta",
            "user_agent": "StarChef Cliente/1.0",
            "timeout_seconds": 12,
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["api_token_configured"] is True
    assert response.data["is_ready"] is True
    assert "api_token" not in response.data
    account.cosmos_config.refresh_from_db()
    assert account.cosmos_config.api_token == "token-da-conta"
    assert account.cosmos_config.user_agent == "StarChef Cliente/1.0"


def test_blank_cosmos_token_preserves_saved_secret(admin_client, account):
    enable_financeiro(account)
    config = account.cosmos_config
    config.api_token = "manter-token"
    config.user_agent = "Agente/1.0"
    config.is_active = True
    config.save()

    response = admin_client.patch(
        "/api/v1/integrations/cosmos/config/",
        {"api_token": "", "timeout_seconds": 20},
        format="json",
    )

    assert response.status_code == 200, response.data
    config.refresh_from_db()
    assert config.api_token == "manter-token"
    assert config.timeout_seconds == 20


def test_cosmos_cannot_be_activated_without_credentials(admin_client, account):
    enable_financeiro(account)

    response = admin_client.patch(
        "/api/v1/integrations/cosmos/config/",
        {"is_active": True},
        format="json",
    )

    assert response.status_code == 400
    assert "api_token" in response.data["error"]["message"]


def test_non_admin_cannot_read_cosmos_config(api_client, account):
    enable_financeiro(account)

    response = api_client.get("/api/v1/integrations/cosmos/config/")

    assert response.status_code == 403
