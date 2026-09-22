"""Os exemplos de estação devem abrir um quadro pronto para operar."""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.core.tenant import tenant_context
from apps.kitchen.models import KdsColumn, KdsItemPosition, KdsStation
from apps.orders.models import Order, OrderItem
from apps.orders.services import (
    add_order_item, cancel_order, create_order, send_order_to_kitchen, update_order_item_status, void_order_item,
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
    assert any(rule["action"] == "exclude" for rule in rules)
    if modelo == "cozinha":
        cancelled = next(column for column in station["columns"] if column["name"] == "Cancelados")
        assert cancelled["is_done"] is False
        assert any(rule["action"] == "move" and rule["target_column"] == cancelled["id"] for rule in rules)
    else:
        assert any(rule["action"] == "exclude" and rule["conditions"] == [
            {"field": "item_status", "operator": "equals", "value": "cancelled"}
        ] for rule in rules)
    columns = {column["id"] for column in station["columns"]}
    assert all(rule["target_column"] in columns for rule in rules if rule["action"] == "move")
    with tenant_context(account):
        sla = ServiceLevelAgreement.objects.get(stations__pk=station["id"])
    assert sla.target_minutes == 18
    assert 0 < sla.alert_minutes < sla.target_minutes

    listed = _client(manager_user).get("/api/v1/kitchen/stations/", {"page_size": 200})
    assert listed.status_code == 200
    stations = listed.data.get("results", listed.data)
    assert next(item for item in stations if item["id"] == station["id"])["rules"] == rules


def test_cozinha_mostra_item_cancelado_na_coluna_sem_reabrir_o_status(
    account, restaurant, branch, product, manager_user
):
    """O KDS descartava itens cancelados antes das regras moverem o card."""
    client = _client(manager_user)
    station = client.post(
        "/api/v1/kitchen/stations/from-template/",
        {"template": "cozinha", "restaurant": str(restaurant.pk)}, format="json",
    ).data
    cancelled_column = next(column for column in station["columns"] if column["name"] == "Cancelados")
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    item = add_order_item(order=order, product=product, quantity=1, user=manager_user)
    send_order_to_kitchen(order, manager_user)
    blocked = client.post(
        f"/api/v1/kitchen/items/{item.id}/move/", {"column": cancelled_column["id"]}, format="json",
    )
    assert blocked.status_code == 409
    void_order_item(item, manager_user, reason="Cliente desistiu")

    url = f"/api/v1/kitchen/items/?station={station['id']}"
    response = client.get(url)
    assert response.status_code == 200, response.content
    items = response.data.get("results", response.data)
    assert next(found for found in items if found["id"] == str(item.id))["kds_position"] == cancelled_column["id"]
    with tenant_context(account):
        item.refresh_from_db()
    assert item.status == OrderItem.STATUS_CANCELLED


def test_cozinha_mostra_itens_quando_o_pedido_inteiro_e_cancelado(
    account, restaurant, branch, product, manager_user
):
    """Cancelar o pedido atualiza itens em lote, que também devem ir para Cancelados."""
    client = _client(manager_user)
    station = client.post(
        "/api/v1/kitchen/stations/from-template/",
        {"template": "cozinha", "restaurant": str(restaurant.pk)}, format="json",
    ).data
    cancelled = next(column for column in station["columns"] if column["name"] == "Cancelados")
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    item = add_order_item(order=order, product=product, quantity=1, user=manager_user)
    send_order_to_kitchen(order, manager_user)
    cancel_order(order, manager_user, reason="Cliente desistiu")

    response = client.get(f"/api/v1/kitchen/items/?station={station['id']}")
    assert response.status_code == 200, response.data
    items = response.data.get("results", response.data)
    assert next(found for found in items if found["id"] == str(item.id))["kds_position"] == cancelled["id"]
    with tenant_context(account):
        item.refresh_from_db()
    assert item.status == OrderItem.STATUS_CANCELLED


def test_exemplo_recusa_sla_de_zero_minutos(restaurant, manager_user):
    """Um SLA sem duração impediria o alerta do quadro de funcionar."""
    response = _client(manager_user).post(
        "/api/v1/kitchen/stations/from-template/",
        {"template": "cozinha", "restaurant": str(restaurant.pk), "sla_minutes": 0},
        format="json",
    )
    assert response.status_code == 400


def test_estacao_antiga_recebe_regras_no_editor_sem_perder_colunas(account, restaurant, manager_user):
    """Estações criadas antes dos modelos continuavam sem regras na tela."""
    with tenant_context(account):
        station = KdsStation.objects.create(account=account, restaurant=restaurant, name="Cozinha antiga")
        KdsColumn.objects.create(account=account, station=station, name="Entrada", is_entry=True)
        KdsColumn.objects.create(account=account, station=station, name="Saída", is_done=True, position=1)
    client = _client(manager_user)
    response = client.post(
        f"/api/v1/kitchen/stations/{station.pk}/apply-template-rules/", {"template": "cozinha"}, format="json",
    )
    assert response.status_code == 200, response.content
    columns = response.data["columns"]
    assert {column["name"] for column in columns} == {"Entrada", "Saída", "Cancelados"}
    assert any(rule["id"] == "move-cancelled" for rule in response.data["rules"])
    again = client.get(f"/api/v1/kitchen/stations/{station.pk}/")
    assert again.data["rules"] == response.data["rules"]
    assert client.post(
        f"/api/v1/kitchen/stations/{station.pk}/apply-template-rules/", {"template": "cozinha"}, format="json",
    ).status_code == 200
    with tenant_context(account):
        assert KdsColumn.objects.filter(station=station, name="Cancelados").count() == 1
        station.refresh_from_db()
        station.rules = [{"id": "own", "name": "Minha regra", "action": "include", "conditions": []}]
        station.save(update_fields=["rules"])
    assert client.post(
        f"/api/v1/kitchen/stations/{station.pk}/apply-template-rules/", {"template": "cozinha"}, format="json",
    ).status_code == 409


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
