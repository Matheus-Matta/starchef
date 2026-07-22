"""Cadastro de estação KDS vincula o restaurante escolhido (não read-only)."""
import pytest

pytestmark = pytest.mark.django_db


def test_create_kds_station_with_selected_restaurant(api_client, restaurant):
    resp = api_client.post(
        "/api/v1/kitchen/stations/",
        {"name": "Cozinha", "restaurant": str(restaurant.id), "sla_minutes": 15},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert str(resp.data["restaurant"]) == str(restaurant.id)
