"""Smoke tests do app invoices. Requer o módulo `financeiro` habilitado na
conta (`Account.enabled_modules`), senão `HasModulePermission` bloqueia com 403 —
mesmo comportamento que um restaurante real teria sem o módulo contratado.
"""
import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def account_with_financeiro(account):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    return account


def test_invoices_list_requires_financeiro_module(api_client):
    resp = api_client.get("/api/v1/invoices/")
    assert resp.status_code == 403


def test_invoices_list_ok_with_module_enabled(api_client, account_with_financeiro):
    resp = api_client.get("/api/v1/invoices/")
    assert resp.status_code == 200


def test_fiscal_config_list_ok_with_module_enabled(api_client, account_with_financeiro):
    resp = api_client.get("/api/v1/fiscal/config/")
    assert resp.status_code == 200


def test_fiscal_profiles_list_ok_with_module_enabled(api_client, account_with_financeiro):
    resp = api_client.get("/api/v1/fiscal/profiles/")
    assert resp.status_code == 200
