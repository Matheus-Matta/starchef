"""Smoke tests do app stock. Requer o módulo `logistica` habilitado na conta,
senão `HasModulePermission` bloqueia com 403 (mesmo padrão do app invoices)."""
import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def account_with_logistica(account):
    account.enabled_modules = ["logistica"]
    account.save(update_fields=["enabled_modules"])
    return account


def test_stock_locations_requires_logistica_module(api_client):
    resp = api_client.get("/api/v1/stock/locations/")
    assert resp.status_code == 403


def test_stock_locations_list_ok_with_module_enabled(api_client, account_with_logistica):
    resp = api_client.get("/api/v1/stock/locations/")
    assert resp.status_code == 200


def test_stock_movements_list_ok_with_module_enabled(api_client, account_with_logistica):
    resp = api_client.get("/api/v1/stock/movements/")
    assert resp.status_code == 200


def test_stock_alerts_ok_with_module_enabled(api_client, account_with_logistica):
    resp = api_client.get("/api/v1/stock/alerts/")
    assert resp.status_code == 200
