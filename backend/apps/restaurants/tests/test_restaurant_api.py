"""CNPJ do restaurante é opcional (vários restaurantes podem ficar sem CNPJ)."""

import importlib

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.hashers import check_password, make_password

from apps.restaurants.admin import RestaurantAdminForm

pytestmark = pytest.mark.django_db


def test_create_restaurant_without_cnpj(admin_client):
    resp = admin_client.post(
        "/api/v1/restaurants/", {"trade_name": "Sem CNPJ 1", "legal_name": "Sem CNPJ 1 LTDA"}, format="json"
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["cnpj"] is None


def test_multiple_restaurants_without_cnpj_do_not_clash(admin_client):
    r1 = admin_client.post("/api/v1/restaurants/", {"trade_name": "Sem CNPJ A", "legal_name": "A LTDA"}, format="json")
    r2 = admin_client.post("/api/v1/restaurants/", {"trade_name": "Sem CNPJ B", "legal_name": "B LTDA"}, format="json")
    assert r1.status_code == 201, r1.data
    assert r2.status_code == 201, r2.data


def test_blank_cnpj_normalized_to_null(admin_client):
    resp = admin_client.post(
        "/api/v1/restaurants/", {"trade_name": "Vazio", "legal_name": "Vazio LTDA", "cnpj": ""}, format="json"
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["cnpj"] is None


def test_restaurant_accepts_district_and_mirrors_it_to_branch(admin_client, restaurant):
    from apps.restaurants.models import Branch

    response = admin_client.patch(
        f"/api/v1/restaurants/{restaurant.id}/",
        {"district": "Centro"},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["district"] == "Centro"
    restaurant.refresh_from_db()
    assert restaurant.district == "Centro"
    mirrored_branch = Branch.all_objects.filter(restaurant=restaurant).order_by("created_at").first()
    assert mirrored_branch.district == "Centro"


def test_cash_action_password_accepts_plain_value_and_returns_only_status(admin_client, restaurant):
    response = admin_client.patch(
        f"/api/v1/restaurants/{restaurant.id}/",
        {"cash_action_password": "123"},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert "cash_action_password" not in response.data
    assert response.data["has_cash_action_password"] is True
    restaurant.refresh_from_db()
    assert restaurant.cash_action_password != "123"
    assert check_password("123", restaurant.cash_action_password)


def test_blank_cash_action_password_keeps_current_password(admin_client, restaurant):
    restaurant.cash_action_password = make_password("123")
    restaurant.save(update_fields=["cash_action_password", "updated_at"])
    previous_hash = restaurant.cash_action_password

    response = admin_client.patch(
        f"/api/v1/restaurants/{restaurant.id}/",
        {"cash_action_password": ""},
        format="json",
    )

    assert response.status_code == 200, response.data
    restaurant.refresh_from_db()
    assert restaurant.cash_action_password == previous_hash


def test_model_hashes_plain_cash_action_password_from_admin_or_script(restaurant):
    restaurant.cash_action_password = "123"
    restaurant.save(update_fields=["cash_action_password", "updated_at"])

    restaurant.refresh_from_db()
    assert restaurant.cash_action_password != "123"
    assert check_password("123", restaurant.cash_action_password)


def test_admin_password_field_does_not_render_current_hash(restaurant):
    restaurant.set_cash_action_password("123")
    restaurant.save(update_fields=["cash_action_password", "updated_at"])

    rendered_field = str(RestaurantAdminForm(instance=restaurant)["cash_action_password"])

    assert restaurant.cash_action_password not in rendered_field
    assert 'type="password"' in rendered_field


def test_data_migration_hashes_plain_password_already_in_database(restaurant):
    # `update` ignora Restaurant.save e reproduz uma base antiga que guardou o
    # texto diretamente pelo Admin ou por um script.
    type(restaurant).all_objects.filter(pk=restaurant.pk).update(cash_action_password="123")
    migration = importlib.import_module("apps.restaurants.migrations.0003_hash_plain_cash_action_passwords")

    migration.hash_plain_cash_action_passwords(django_apps, None)

    restaurant.refresh_from_db()
    assert restaurant.cash_action_password != "123"
    assert check_password("123", restaurant.cash_action_password)


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
