"""Testes do módulo SLA (Sprint 6 · STC-065/066)."""
import uuid

import pytest

from apps.restaurants.models import Restaurant
from apps.sla.models import ServiceLevelAgreement

pytestmark = pytest.mark.django_db


def sla_payload(**overrides):
    data = {"name": "SLA Preparo", "sla_type": "prep", "target_minutes": 15, "alert_minutes": 10}
    data.update(overrides)
    return data


def test_create_sla(admin_client):
    resp = admin_client.post("/api/v1/sla/", sla_payload(), format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["sla_type"] == "prep"


def test_alert_cannot_exceed_target(admin_client):
    resp = admin_client.post("/api/v1/sla/", sla_payload(target_minutes=10, alert_minutes=20), format="json")
    assert resp.status_code == 400
    assert "alert_minutes" in resp.data["error"]["message"]


def test_sla_linked_to_multiple_restaurants(admin_client, account, restaurant):
    other = Restaurant.objects.create(
        account=account, legal_name="Outro LTDA", trade_name="Outro", cnpj=f"{uuid.uuid4().int % 10**14:014d}"
    )
    resp = admin_client.post(
        "/api/v1/sla/",
        sla_payload(restaurants=[str(restaurant.id), str(other.id)]),
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert len(resp.data["restaurants"]) == 2


def test_conflicting_sla_same_type_and_restaurant(admin_client, account, restaurant):
    admin_client.post("/api/v1/sla/", sla_payload(restaurants=[str(restaurant.id)]), format="json")
    resp = admin_client.post(
        "/api/v1/sla/",
        sla_payload(name="Outro SLA", restaurants=[str(restaurant.id)]),
        format="json",
    )
    assert resp.status_code == 400
    assert "restaurants" in resp.data["error"]["message"]


def test_sla_isolated_by_account(admin_client, account, restaurant):
    ServiceLevelAgreement.objects.create(account=account, name="Meu SLA", sla_type="prep")
    from apps.accounts.models import Account
    other_account = Account.objects.create(name="X", slug=f"x-{uuid.uuid4().hex[:8]}")
    ServiceLevelAgreement.objects.create(account=other_account, name="SLA Alheio", sla_type="prep")

    resp = admin_client.get("/api/v1/sla/")
    names = [row["name"] for row in resp.data["results"]]
    assert "Meu SLA" in names
    assert "SLA Alheio" not in names
