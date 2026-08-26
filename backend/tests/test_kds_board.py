"""Quadro do KDS: colunas por estação, mover card (drag) e efeitos de status."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.kitchen.models import KdsColumn, KdsStation
from apps.orders.models import Order, OrderItem
from apps.orders.services import add_order_item, create_order, dispatch_kitchen_batch, send_order_to_kitchen

pytestmark = pytest.mark.django_db


@pytest.fixture
def station(account, restaurant):
    return KdsStation.objects.create(account=account, restaurant=restaurant, name="Cozinha", sla_minutes=15)


@pytest.fixture
def entry_column(account, station):
    return KdsColumn.objects.create(account=account, station=station, name="A fazer", position=0, is_entry=True)


@pytest.fixture
def done_column(account, station):
    return KdsColumn.objects.create(account=account, station=station, name="Pronto", position=2, is_done=True)


@pytest.fixture
def sent_item(restaurant, branch, table, product, manager_user):
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_TABLE, table=table, user=manager_user)
    item = add_order_item(order=order, product=product, quantity=1, user=manager_user)
    send_order_to_kitchen(order, manager_user)
    item.refresh_from_db()
    item.batch.dispatch_at = timezone.now() - timedelta(seconds=1)
    item.batch.save(update_fields=["dispatch_at", "updated_at"])
    dispatch_kitchen_batch(item.batch)
    item.refresh_from_db()
    return item


def _client(user):
    from rest_framework.test import APIClient

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    return client


def test_station_lists_nested_columns(manager_user, station, entry_column, done_column):
    resp = _client(manager_user).get("/api/v1/kitchen/stations/")
    assert resp.status_code == 200, resp.data
    row = next(s for s in resp.data["results"] if s["id"] == str(station.id))
    names = {c["name"] for c in row["columns"]}
    assert {"A fazer", "Pronto"} <= names


def test_columns_filtered_by_station(manager_user, station, entry_column):
    resp = _client(manager_user).get(f"/api/v1/kitchen/columns/?station={station.id}")
    assert resp.status_code == 200, resp.data
    rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
    assert any(c["id"] == str(entry_column.id) and c["label"] == "Cozinha · A fazer" for c in rows)


def test_move_to_done_column_marks_item_ready(manager_user, sent_item, entry_column, done_column):
    client = _client(manager_user)
    # Move para a coluna final → conclui (marca "pronto") e grava a coluna.
    resp = client.post(f"/api/v1/kitchen/items/{sent_item.id}/move/", {"column": str(done_column.id)}, format="json")
    assert resp.status_code == 200, resp.data

    sent_item.refresh_from_db()
    assert sent_item.kds_column_id == done_column.id
    assert sent_item.status == OrderItem.STATUS_READY
    assert sent_item.ready_at is not None


def test_move_off_entry_starts_preparing(manager_user, sent_item, entry_column, done_column):
    client = _client(manager_user)
    middle = KdsColumn.objects.create(account=sent_item.account, station=entry_column.station, name="Preparo", position=1)
    resp = client.post(f"/api/v1/kitchen/items/{sent_item.id}/move/", {"column": str(middle.id)}, format="json")
    assert resp.status_code == 200, resp.data

    sent_item.refresh_from_db()
    assert sent_item.kds_column_id == middle.id
    assert sent_item.status == OrderItem.STATUS_PREPARING


def test_items_date_filter(manager_user, sent_item):
    import datetime

    client = _client(manager_user)
    today = datetime.date.today().isoformat()
    past = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()

    r_today = client.get(f"/api/v1/kitchen/items/?launched_after={today}&launched_before={today}")
    assert any(i["id"] == str(sent_item.id) for i in r_today.data["results"])

    r_past = client.get(f"/api/v1/kitchen/items/?launched_after={past}&launched_before={past}")
    assert all(i["id"] != str(sent_item.id) for i in r_past.data["results"])


def test_list_station_templates(manager_user):
    resp = _client(manager_user).get("/api/v1/kitchen/stations/templates/")
    assert resp.status_code == 200, resp.data
    keys = {t["key"] for t in resp.data}
    assert {"cozinha", "bar"} <= keys


def test_create_station_from_template(manager_user, restaurant):
    resp = _client(manager_user).post(
        "/api/v1/kitchen/stations/from-template/",
        {"template": "cozinha", "name": "Cozinha 1", "restaurant": str(restaurant.id)},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["name"] == "Cozinha 1"
    cols = resp.data["columns"]
    assert [c["name"] for c in sorted(cols, key=lambda c: c["position"])] == ["A fazer", "Em preparo", "Montagem", "Pronto"]
    assert cols[0]["is_entry"] is True
    assert any(c["is_done"] for c in cols)


def test_create_from_template_rejects_bad_template(manager_user, restaurant):
    resp = _client(manager_user).post(
        "/api/v1/kitchen/stations/from-template/",
        {"template": "inexistente", "restaurant": str(restaurant.id)},
        format="json",
    )
    assert resp.status_code == 400, resp.data


def test_move_rejects_column_from_other_account(manager_user, sent_item):
    from apps.accounts.models import Account
    from apps.restaurants.models import Restaurant

    other = Account.objects.create(name="Outra", slug="outra-conta")
    other_rest = Restaurant.objects.create(account=other, legal_name="X", trade_name="X", cnpj="11.111.111/1111-11")
    other_station = KdsStation.objects.create(account=other, restaurant=other_rest, name="Outro")
    other_col = KdsColumn.objects.create(account=other, station=other_station, name="Nope", position=0)

    resp = _client(manager_user).post(
        f"/api/v1/kitchen/items/{sent_item.id}/move/", {"column": str(other_col.id)}, format="json"
    )
    assert resp.status_code == 400, resp.data
