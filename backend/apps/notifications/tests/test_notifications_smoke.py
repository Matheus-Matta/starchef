"""Smoke test do app notifications: listagem responde sem 500 (módulo base, sem gate)."""
import pytest

pytestmark = pytest.mark.django_db


def test_notifications_list_ok(api_client):
    resp = api_client.get("/api/v1/notifications/")
    assert resp.status_code == 200
