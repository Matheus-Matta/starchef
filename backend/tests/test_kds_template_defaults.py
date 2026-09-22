"""Os exemplos de estação devem abrir um quadro pronto para operar."""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.core.tenant import tenant_context
from apps.kitchen.models import KdsItemPosition
from apps.orders.models import Order, OrderItem
from apps.orders.services import (
    add_order_item, create_order, send_order_to_kitchen, update_order_item_status,
)
from apps.sla.models import ServiceLevelAgreement


pytestmark = pytest.mark.django_db


def _client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    return client


@pytest.mark.parametrize("modelo", ["cozinha", "bar", "pizzaria", "confeitaria", "simples"])
def test_exemplo_cria_regras_e_alerta_sla(account, restaurant, manager_user, modelo):
    """Só definir o número de minutos não ativava alerta nem fluxo no KDS."""
    response = _client(manager_user).post(
        "/api/v1/kitchen/stations/from-template/",
        {"template": modelo, "restaurant": str(restaurant.pk), "sla_minutes": 18},
        format="json",
    )

    assert response.status_code == 201, response.data
    station = response.data
    rules = station["rules"]
    assert {rule["action"] for rule in rules} == {"include", "exclude", "move"}
    assert any(
        rule["action"] == "exclude" and
        rule["conditions"][0]["field"] == "order_status" and
        rule["conditions"][0]["value"] == "cancelled"
        for rule in rules
    )
    assert any(rule["conditions"] == [
        {"field": "item_status", "operator": "equals", "value": "cancelled"}
    ] for rule in rules)
    columns = {column["id"] for column in station["columns"]}
    assert all(rule["target_column"] in columns for rule in rules if rule["action"] == "move")
    with tenant_context(account):
        sla = ServiceLevelAgreement.objects.get(stations__pk=station["id"])
    assert sla.target_minutes == 18
    assert 0 < sla.alert_minutes < sla.target_minutes


def test_exemplo_recusa_sla_de_zero_minutos(restaurant, manager_user):
    """Um SLA sem duração impediria o alerta do quadro de funcionar."""
    response = _client(manager_user).post(
        "/api/v1/kitchen/stations/from-template/",
        {"template": "cozinha", "restaurant": str(restaurant.pk), "sla_minutes": 0},
        format="json",
    )
    assert response.status_code == 400


def test_exemplo_respeita_movimento_manual_e_conclui_item_pronto(
    account, restaurant, branch, product, manager_user
):
    """Uma regra de preparo não pode voltar um card que já chegou à montagem."""
    client = _client(manager_user)
    station = client.post(
        "/api/v1/kitchen/stations/from-template/",
        {"template": "cozinha", "restaurant": str(restaurant.pk)},
        format="json",
    ).data
    columns = {column["name"]: column["id"] for column in station["columns"]}
    order = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user
    )
    item = add_order_item(order=order, product=product, quantity=1, user=manager_user)
    send_order_to_kitchen(order, manager_user)
    url = f"/api/v1/kitchen/items/?station={station['id']}"

    assert client.get(url).status_code == 200
    with tenant_context(account):
        position = KdsItemPosition.objects.get(station_id=station["id"], item=item)
    assert str(position.column_id) == columns["A fazer"]
    item.refresh_from_db()
    assert item.status == OrderItem.STATUS_SENT

    update_order_item_status(item, OrderItem.STATUS_PREPARING, manager_user)
    assert client.get(url).status_code == 200
    position.refresh_from_db()
    assert str(position.column_id) == columns["Em preparo"]

    moved = client.post(
        f"/api/v1/kitchen/items/{item.id}/move/", {"column": columns["Montagem"]}, format="json"
    )
    assert moved.status_code == 200, moved.data
    assert client.get(url).status_code == 200
    position.refresh_from_db()
    assert str(position.column_id) == columns["Montagem"]

    item.refresh_from_db()
    update_order_item_status(item, OrderItem.STATUS_READY, manager_user)
    assert client.get(url).status_code == 200
    position.refresh_from_db()
    assert str(position.column_id) == columns["Pronto"]
