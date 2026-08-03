"""Smoke tests do app reports: cada endpoint de relatório responde sem 500,
sem parâmetros de data (todos são opcionais)."""
import pytest

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/reports/dashboard/",
        "/api/v1/reports/sales/",
        "/api/v1/reports/orders/",
        "/api/v1/reports/products/",
        "/api/v1/reports/payments/",
        "/api/v1/reports/waiters/",
        "/api/v1/reports/restaurants/",
    ],
)
def test_report_endpoint_ok(api_client, path):
    resp = api_client.get(path)
    assert resp.status_code == 200
