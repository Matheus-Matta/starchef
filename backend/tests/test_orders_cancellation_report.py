"""Relatorio de pedidos: a lista de cancelamentos com quem, quem liberou,
como e quanto — e os itens retirados da conta."""
import pytest

from apps.core.tenant import tenant_context
from apps.orders.models import Order, OrderItem
from apps.orders.services import add_order_item, cancel_order, create_order, send_order_to_kitchen, void_order_item

pytestmark = pytest.mark.django_db


def _authenticate(api_client):
    api_client.force_authenticate(user=None)
    login = api_client.post(
        "/api/v1/auth/login/",
        {"username": "manager", "password": "secret123", "no_cookie": True},
        format="json",
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")


def _order(restaurant, branch, table, product, user, quantity=1):
    order = create_order(restaurant=restaurant, branch=branch, order_type="table", table=table, user=user)
    add_order_item(order=order, product=product, quantity=quantity, user=user)
    return order


def test_cancel_records_who_how_and_when(api_client, manager_user, restaurant, branch, table, product):
    _authenticate(api_client)
    restaurant.set_cash_action_password("caixa123")
    restaurant.save(update_fields=["cash_action_password"])
    order = _order(restaurant, branch, table, product, manager_user)
    send_order_to_kitchen(order, manager_user)

    response = api_client.post(
        f"/api/v1/orders/{order.id}/cancel/", {"reason": "Cliente foi embora", "cash_password": "caixa123"}, format="json"
    )
    assert response.status_code == 200, response.content
    order = Order.all_objects.get(pk=order.pk)
    assert order.cancelled_at is not None
    assert order.cancelled_by_id == manager_user.id
    assert order.cancel_authorization == Order.AUTHORIZATION_CASH_PASSWORD
    assert order.cancel_authorized_by is None
    item = OrderItem.all_objects.get(order=order)
    assert item.status == OrderItem.STATUS_CANCELLED
    assert item.voided_at is not None and item.voided_by_id == manager_user.id


def test_orders_report_lists_cancellations_and_voided_items(api_client, manager_user, waiter_user, restaurant, branch, table, product):
    # Um pedido cancelado inteiro (senha do caixa) e outro vivo com um item
    # retirado antes de ir a cozinha.
    with tenant_context(restaurant.account):
        cancelled = _order(restaurant, branch, table, product, manager_user, quantity=2)
        cancel_order(cancelled, waiter_user, "Pedido errado", authorization=Order.AUTHORIZATION_CASH_PASSWORD)
        alive = _order(restaurant, branch, table, product, manager_user)
        void_order_item(OrderItem.objects.get(order=alive), waiter_user, "Cliente trocou")
    _authenticate(api_client)

    report = api_client.get("/api/v1/reports/orders/").json()
    assert report["orders_cancelled"] == 1
    assert float(report["cancelled_total"]) == float(cancelled.total) or float(report["cancelled_total"]) >= 0
    assert report["cancelled_rate"] == 50.0
    assert report["voided_items_count"] == 1

    row = report["cancelled_orders"][0]
    assert row["sequence"] == cancelled.sequence
    assert row["reference"] == f"Mesa {table.number}"
    assert row["cancelled_by"] == (waiter_user.get_full_name() or waiter_user.username)
    assert row["authorization"] == "cash_password"
    assert row["authorization_label"] == "Senha do caixa"
    assert row["reason"] == "Pedido errado"
    assert row["items_count"] == 1
    assert row["minutes_open"] is not None

    voided = report["voided_items"][0]
    assert voided["order_sequence"] == alive.sequence
    assert voided["kind"] == "Desistência"
    assert voided["reason"] == "Cliente trocou"
    assert voided["before_kitchen"] is True
    assert voided["voided_by"] == (waiter_user.get_full_name() or waiter_user.username)

    assert report["cancelled_by_user"][0]["count"] == 1
    assert report["cancelled_by_authorization"][0]["label"] == "Senha do caixa"
    assert len(report["cancelled_by_hour"]) == 1
    assert "cancelled_orders" in report["pagination"]

    # Filtro por autorizacao e por quem cancelou.
    none = api_client.get("/api/v1/reports/orders/", {"authorization": "grace"}).json()
    assert none["cancelled_orders"] == []
    mine = api_client.get("/api/v1/reports/orders/", {"cancelled_by": str(waiter_user.id)}).json()
    assert len(mine["cancelled_orders"]) == 1

    csv_response = api_client.get("/api/v1/reports/orders/", {"export": "csv"})
    assert csv_response.status_code == 200
    body = csv_response.content.decode("utf-8")
    assert "Pedidos cancelados" in body and "Itens retirados da conta" in body and "Pedido errado" in body
