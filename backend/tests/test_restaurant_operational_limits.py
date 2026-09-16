"""Configuracoes operacionais do restaurante: limite de comandas por mesa e
carencia de cancelamento. As duas viviam improvisadas (capacidade da mesa no
PDV; carencia desligada no backend) e agora sao regra do cadastro."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.orders.models import OrderBatch, OrderItem
from apps.orders.services import add_order_item, create_order, order_within_cancellation_grace, send_order_to_kitchen
from apps.restaurants.models import Command, Table

pytestmark = pytest.mark.django_db


def _authenticate(api_client):
    api_client.force_authenticate(user=None)
    login = api_client.post(
        "/api/v1/auth/login/",
        {"username": "manager", "password": "secret123", "no_cookie": True},
        format="json",
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")


def _commands(account, restaurant, branch, count):
    return [Command.objects.create(account=account, restaurant=restaurant, branch=branch) for _ in range(count)]


# ── comandas por mesa ───────────────────────────────────────────────────


def test_restaurant_exposes_and_edits_operational_settings(api_client, manager_user, restaurant):
    _authenticate(api_client)
    current = api_client.get(f"/api/v1/restaurants/{restaurant.id}/").json()
    assert current["max_commands_per_table"] == 4
    assert current["cancellation_grace_seconds"] == 0

    updated = api_client.patch(
        f"/api/v1/restaurants/{restaurant.id}/",
        {"max_commands_per_table": 2, "cancellation_grace_seconds": 90},
        format="json",
    )
    assert updated.status_code == 200, updated.content
    restaurant.refresh_from_db()
    assert restaurant.max_commands_per_table == 2
    assert restaurant.cancellation_grace_seconds == 90


def test_link_table_respects_the_restaurant_limit(api_client, manager_user, account, restaurant, branch, table):
    _authenticate(api_client)
    restaurant.max_commands_per_table = 2
    restaurant.save(update_fields=["max_commands_per_table"])
    first, second, third = _commands(account, restaurant, branch, 3)

    for command in (first, second):
        response = api_client.post(f"/api/v1/commands/{command.id}/link-table/", {"table_id": str(table.id)}, format="json")
        assert response.status_code == 200, response.content

    blocked = api_client.post(f"/api/v1/commands/{third.id}/link-table/", {"table_id": str(table.id)}, format="json")
    assert blocked.status_code == 409, blocked.content
    body = blocked.json()
    assert body["error"]["code"] == "limit_reached"
    assert "limite" in str(body["error"]["message"]).lower()
    third.refresh_from_db()
    assert third.current_table_id is None

    # Re-vincular quem ja esta na mesa nao ocupa vaga nova.
    again = api_client.post(f"/api/v1/commands/{second.id}/link-table/", {"table_id": str(table.id)}, format="json")
    assert again.status_code == 200

    # 0 = sem limite.
    restaurant.max_commands_per_table = 0
    restaurant.save(update_fields=["max_commands_per_table"])
    freed = api_client.post(f"/api/v1/commands/{third.id}/link-table/", {"table_id": str(table.id)}, format="json")
    assert freed.status_code == 200


def test_create_with_item_on_a_table_respects_the_limit(api_client, manager_user, account, restaurant, branch, table, product):
    _authenticate(api_client)
    restaurant.max_commands_per_table = 1
    restaurant.save(update_fields=["max_commands_per_table"])
    seated, newcomer = _commands(account, restaurant, branch, 2)
    seated.current_table = table
    seated.save(update_fields=["current_table"])

    response = api_client.post(
        "/api/v1/orders/create-with-item/",
        {
            "order_type": "command",
            "command": str(newcomer.id),
            "table": str(table.id),
            "item": {"product": str(product.id), "quantity": 1},
        },
        format="json",
    )
    assert response.status_code == 409, response.content
    assert response.json()["error"]["code"] == "limit_reached"


def test_transfer_all_commands_respects_the_destination_limit(api_client, manager_user, account, restaurant, branch, table):
    _authenticate(api_client)
    restaurant.max_commands_per_table = 2
    restaurant.save(update_fields=["max_commands_per_table"])
    destination = Table.objects.create(
        account=account, restaurant=restaurant, branch=branch, sector=table.sector, number="2", capacity=4
    )
    moving = _commands(account, restaurant, branch, 2)
    for command in moving:
        command.current_table = table
        command.save(update_fields=["current_table"])
    already_there = _commands(account, restaurant, branch, 1)[0]
    already_there.current_table = destination
    already_there.save(update_fields=["current_table"])

    response = api_client.post(
        f"/api/v1/tables/{table.id}/transfer-commands/",
        {"to_table_id": str(destination.id)},
        format="json",
    )
    assert response.status_code == 409, response.content


# ── carencia de cancelamento ────────────────────────────────────────────


def _order_with_item(restaurant, branch, table, product, user):
    order = create_order(restaurant=restaurant, branch=branch, order_type="table", table=table, user=user)
    add_order_item(order=order, product=product, quantity=1, user=user)
    return order


def test_grace_holds_the_kitchen_round_and_waives_the_password(api_client, manager_user, restaurant, branch, table, product):
    _authenticate(api_client)
    restaurant.cancellation_grace_seconds = 120
    restaurant.save(update_fields=["cancellation_grace_seconds"])
    order = _order_with_item(restaurant, branch, table, product, manager_user)

    send_order_to_kitchen(order, manager_user)
    batch = OrderBatch.all_objects.get(order=order)
    assert batch.status == OrderBatch.STATUS_SCHEDULED
    assert batch.dispatch_at > timezone.now() + timedelta(seconds=100)
    assert OrderItem.all_objects.get(order=order).status == OrderItem.STATUS_QUEUED
    with tenant_context(restaurant.account):
        assert order_within_cancellation_grace(order) is True

    # Sem senha, sem usuario: dentro da carencia cancela direto.
    response = api_client.post(f"/api/v1/orders/{order.id}/cancel/", {"reason": "Cliente desistiu"}, format="json")
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "cancelled"


def test_after_the_grace_the_password_is_required_again(api_client, manager_user, restaurant, branch, table, product):
    _authenticate(api_client)
    restaurant.cancellation_grace_seconds = 60
    restaurant.save(update_fields=["cancellation_grace_seconds"])
    order = _order_with_item(restaurant, branch, table, product, manager_user)
    send_order_to_kitchen(order, manager_user)
    # O relogio anda: a rodada venceu e ja e da cozinha.
    OrderBatch.all_objects.filter(order=order).update(dispatch_at=timezone.now() - timedelta(seconds=1))

    with tenant_context(restaurant.account):
        assert order_within_cancellation_grace(order) is False
    assert OrderItem.all_objects.get(order=order).status == OrderItem.STATUS_SENT

    refused = api_client.post(f"/api/v1/orders/{order.id}/cancel/", {"reason": "Tarde demais"}, format="json")
    assert refused.status_code == 403


def test_without_grace_the_round_goes_out_immediately(manager_user, restaurant, branch, table, product):
    order = _order_with_item(restaurant, branch, table, product, manager_user)
    send_order_to_kitchen(order, manager_user)
    assert OrderBatch.all_objects.get(order=order).status == OrderBatch.STATUS_SENT
    assert OrderItem.all_objects.get(order=order).status == OrderItem.STATUS_SENT
    with tenant_context(restaurant.account):
        assert order_within_cancellation_grace(order) is False


def test_offline_printed_round_ignores_the_grace(manager_user, restaurant, branch, table, product):
    restaurant.cancellation_grace_seconds = 120
    restaurant.save(update_fields=["cancellation_grace_seconds"])
    order = _order_with_item(restaurant, branch, table, product, manager_user)
    send_order_to_kitchen(order, manager_user, offline_printed=True)
    # O papel ja saiu no terminal: segurar a rodada so esconderia do KDS.
    assert OrderBatch.all_objects.get(order=order).status == OrderBatch.STATUS_SENT
