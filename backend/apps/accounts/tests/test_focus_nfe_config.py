import uuid
from importlib import import_module

import pytest
from django.apps import apps
from django.test import override_settings

from apps.accounts.models import Account, FocusNfeConfig

pytestmark = pytest.mark.django_db


@override_settings(
    FOCUS_NFE_MASTER_TOKEN="token-bootstrap",
    FOCUS_NFE_PRODUCTION_URL="https://producao.bootstrap.example",
    FOCUS_NFE_HOMOLOGATION_URL="https://homologacao.bootstrap.example",
    FOCUS_NFE_TIMEOUT_SECONDS=45,
    FOCUS_NFE_AUTO_SYNC=False,
    FOCUS_NFE_COMPANY_DRY_RUN=True,
    FOCUS_NFE_WEBHOOK_URL="https://api.bootstrap.example/focus/webhook/",
    FOCUS_NFE_WEBHOOK_AUTHORIZATION="segredo-bootstrap",
    FOCUS_NFE_WEBHOOK_AUTHORIZATION_HEADER="X-Focus-Auth",
)
def test_new_account_receives_focus_defaults_from_settings():
    account = Account.objects.create(name="Nova conta", slug=f"nova-{uuid.uuid4().hex[:8]}")

    config = FocusNfeConfig.objects.get(account=account)
    assert config.master_token == "token-bootstrap"
    assert config.production_url == "https://producao.bootstrap.example"
    assert config.homologation_url == "https://homologacao.bootstrap.example"
    assert config.timeout_seconds == 45
    assert config.auto_sync is False
    assert config.company_dry_run is True
    assert config.webhook_authorization == "segredo-bootstrap"
    assert config.webhook_authorization_header == "X-Focus-Auth"


@override_settings(
    FOCUS_NFE_MASTER_TOKEN="token-migrado",
    FOCUS_NFE_PRODUCTION_URL="https://producao.migrada.example",
    FOCUS_NFE_HOMOLOGATION_URL="https://homologacao.migrada.example",
)
def test_data_migration_seeds_existing_accounts_from_settings(account):
    FocusNfeConfig.objects.filter(account=account).delete()
    migration = import_module("apps.accounts.migrations.0004_focusnfeconfig")

    migration.seed_focus_nfe_configs(apps, schema_editor=None)

    config = FocusNfeConfig.objects.get(account=account)
    assert config.master_token == "token-migrado"
    assert config.production_url == "https://producao.migrada.example"
    assert config.homologation_url == "https://homologacao.migrada.example"


def test_tenant_admin_can_edit_own_focus_config_without_reading_secrets(admin_client, account):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])

    response = admin_client.patch(
        "/api/v1/integrations/focus-nfe/config/",
        {
            "master_token": "novo-token",
            "production_url": "https://focus.conta.example",
            "homologation_url": "https://homologacao.conta.example",
            "webhook_authorization": "novo-segredo",
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["master_token_configured"] is True
    assert response.data["webhook_authorization_configured"] is True
    assert "master_token" not in response.data
    assert "webhook_authorization" not in response.data
    account.focus_nfe_config.refresh_from_db()
    assert account.focus_nfe_config.master_token == "novo-token"
    assert account.focus_nfe_config.production_url == "https://focus.conta.example"


def test_blank_secret_preserves_current_value(admin_client, account):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    config = account.focus_nfe_config
    config.master_token = "manter-token"
    config.save(update_fields=["master_token", "updated_at"])

    response = admin_client.patch(
        "/api/v1/integrations/focus-nfe/config/",
        {"master_token": "", "timeout_seconds": 55},
        format="json",
    )

    assert response.status_code == 200, response.data
    config.refresh_from_db()
    assert config.master_token == "manter-token"
    assert config.timeout_seconds == 55


def test_non_admin_cannot_read_focus_config(api_client, account):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])

    response = api_client.get("/api/v1/integrations/focus-nfe/config/")

    assert response.status_code == 403
