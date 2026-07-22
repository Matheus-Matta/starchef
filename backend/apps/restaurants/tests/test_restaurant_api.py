"""CNPJ do restaurante é opcional (vários restaurantes podem ficar sem CNPJ)."""
import pytest

pytestmark = pytest.mark.django_db


def test_create_restaurant_without_cnpj(admin_client):
    resp = admin_client.post("/api/v1/restaurants/", {"trade_name": "Sem CNPJ 1", "legal_name": "Sem CNPJ 1 LTDA"}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["cnpj"] is None


def test_multiple_restaurants_without_cnpj_do_not_clash(admin_client):
    r1 = admin_client.post("/api/v1/restaurants/", {"trade_name": "Sem CNPJ A", "legal_name": "A LTDA"}, format="json")
    r2 = admin_client.post("/api/v1/restaurants/", {"trade_name": "Sem CNPJ B", "legal_name": "B LTDA"}, format="json")
    assert r1.status_code == 201, r1.data
    assert r2.status_code == 201, r2.data


def test_blank_cnpj_normalized_to_null(admin_client):
    resp = admin_client.post("/api/v1/restaurants/", {"trade_name": "Vazio", "legal_name": "Vazio LTDA", "cnpj": ""}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["cnpj"] is None


def test_table_blocks_sector_from_another_restaurant(admin_client, account, restaurant):
    import uuid
    from apps.restaurants.models import Restaurant, TableSector

    other = Restaurant.objects.create(
        account=account, legal_name="Outro LTDA", trade_name="Outro", cnpj=f"{uuid.uuid4().int % 10**14:014d}"
    )
    sector_b = TableSector.objects.create(account=account, restaurant=other, name="Salão B")

    resp = admin_client.post(
        "/api/v1/tables/",
        {"number": "1", "restaurant": str(restaurant.id), "sector": str(sector_b.id), "capacity": 4},
        format="json",
    )
    assert resp.status_code == 400, resp.data
    assert "sector" in resp.data["error"]["message"]


def test_table_accepts_sector_from_same_restaurant(admin_client, account, restaurant):
    from apps.restaurants.models import TableSector

    sector_a = TableSector.objects.create(account=account, restaurant=restaurant, name="Salão A")
    resp = admin_client.post(
        "/api/v1/tables/",
        {"number": "2", "restaurant": str(restaurant.id), "sector": str(sector_a.id), "capacity": 4},
        format="json",
    )
    assert resp.status_code == 201, resp.data
