"""Movimentacao do caixa: detalhes por movimento, historico entre sessoes e o
relatorio dedicado — o que o gerente confere no fim da semana."""
from decimal import Decimal

import pytest

from apps.orders.models import Order, OrderItem
from apps.payments.models import CashStation, Payment, PaymentMethod

from tests.test_cash_session_exclusivity import BALCAO_01, client_for, open_via_api

pytestmark = pytest.mark.django_db


@pytest.fixture
def station(account, restaurant, manager_user, waiter_user):
    station = CashStation.objects.create(account=account, restaurant=restaurant, name="Caixa 1", code="CX01")
    station.operators.add(manager_user, waiter_user)
    return station


def _shift_with_movements(client, station, restaurant):
    """Abre com 100, supre 50 (aprovado por senha), sangra 30 (pendente)."""
    restaurant.set_cash_action_password("caixa123")
    restaurant.save(update_fields=["cash_action_password"])
    opened = open_via_api(client, station).json()
    session_id = opened["id"]
    supply = client.post(
        f"/api/v1/cash-register/{session_id}/supply/",
        {"amount": "50.00", "reason": "Troco extra", "source": "Cofre", "terminal_installation_id": BALCAO_01, "terminal_name": "Balcão 01"},
        format="json",
    )
    assert supply.status_code == 201, supply.content
    approved = client.post(
        f"/api/v1/cash-register/{session_id}/approve/",
        {"movement": supply.json()["id"], "reason": "Falta de troco", "cash_password": "caixa123"},
        format="json",
    )
    assert approved.status_code == 200, approved.content
    withdrawal = client.post(
        f"/api/v1/cash-register/{session_id}/withdrawal/",
        {"amount": "30.00", "reason": "Malote", "destination": "Cofre", "terminal_installation_id": BALCAO_01},
        format="json",
    )
    assert withdrawal.status_code == 201, withdrawal.content
    return session_id


def test_movement_carries_who_where_and_running_balance(station, restaurant, manager_user):
    client = client_for(manager_user, BALCAO_01)
    session_id = _shift_with_movements(client, station, restaurant)

    session = client.get(f"/api/v1/cash-register/{session_id}/").json()
    movements = session["movements"]
    assert [m["movement_type"] for m in movements] == ["opening", "supply", "withdrawal"]
    opening, supply, withdrawal = movements
    assert opening["balance_after"] == "100.00"
    assert supply["balance_after"] == "150.00"
    # A sangria pendente ainda nao mexeu na gaveta.
    assert withdrawal["balance_after"] == "150.00"
    assert withdrawal["status"] == "pending"
    assert withdrawal["authorization"] == "pending"
    assert supply["authorization"] == "cash_password"
    assert supply["authorized_by_name"] == manager_user.get_full_name() or manager_user.username
    assert supply["manager_reason"] == "Falta de troco"
    assert supply["operator_name"]
    assert supply["terminal_label"] == "Balcão 01"
    assert supply["cash_station_name"] == "Caixa 1"


def test_cash_movements_history_filters_and_csv(station, restaurant, manager_user):
    client = client_for(manager_user, BALCAO_01)
    _shift_with_movements(client, station, restaurant)

    listed = client.get("/api/v1/cash-movements/", {"movement_type": "supply"}).json()
    assert listed["count"] == 1
    assert listed["results"][0]["reason"] == "Troco extra"

    by_station = client.get("/api/v1/cash-movements/", {"cash_station": str(station.id)}).json()
    assert by_station["count"] == 3

    csv_response = client.get("/api/v1/cash-movements/", {"export": "csv"})
    assert csv_response.status_code == 200
    body = csv_response.content.decode("utf-8")
    assert "Suprimento" in body and "Sangria" in body and "Senha do caixa" in body


def test_cash_movements_report_sums_only_approved(station, restaurant, manager_user):
    client = client_for(manager_user, BALCAO_01)
    _shift_with_movements(client, station, restaurant)

    report = client.get("/api/v1/reports/cash-movements/").json()
    summary = report["summary"]
    assert Decimal(str(summary["opening"])) == Decimal("100.00")
    assert Decimal(str(summary["supplies"])) == Decimal("50.00")
    # Sangria pendente nao e dinheiro que saiu.
    assert Decimal(str(summary["withdrawals"])) == Decimal("0")
    assert summary["pending_count"] == 1
    assert summary["movements_count"] == 3
    assert summary["sessions_count"] == 1
    assert [row["label"] for row in report["by_type"]] == ["Abertura", "Suprimento"]
    assert report["by_station"][0]["cash_station_name"] == "Caixa 1"
    assert report["by_operator"][0]["count"] == 2
    assert len(report["by_day"]) == 1
    assert report["sessions"][0]["status"] == "open"
    assert report["pagination"]["movements"]["count"] == 3

    csv_response = client.get("/api/v1/reports/cash-movements/", {"export": "csv"})
    assert csv_response.status_code == 200
    assert "Movimentação do caixa" in csv_response.content.decode("utf-8")

    bad = client.get("/api/v1/reports/cash-movements/", {"date_from": "2026-13-01"})
    assert bad.status_code == 400


def test_cash_session_statement_includes_orders_and_items(
    station, restaurant, branch, manager_user, product
):
    client = client_for(manager_user, BALCAO_01)
    session_id = _shift_with_movements(client, station, restaurant)
    order = Order.objects.create(
        account=station.account,
        restaurant=restaurant,
        branch=branch,
        sequence=91,
        order_type=Order.TYPE_COUNTER,
        status=Order.STATUS_PAID,
        payment_status=Order.PAYMENT_PAID,
        responsible_user=manager_user,
        total="25.00",
    )
    item = OrderItem.objects.create(
        account=station.account,
        restaurant=restaurant,
        branch=branch,
        order=order,
        product=product,
        quantity="1.000",
        unit_price="25.00",
        total_price="25.00",
        production_sector=product.production_sector,
        status=OrderItem.STATUS_DELIVERED,
    )
    method = PaymentMethod.objects.create(
        account=station.account,
        restaurant=restaurant,
        branch=branch,
        name="PIX",
        method_type=PaymentMethod.TYPE_PIX,
    )
    Payment.objects.create(
        account=station.account,
        restaurant=restaurant,
        branch=branch,
        order=order,
        payment_method=method,
        amount="25.00",
        metadata={"cash_register": session_id},
    )

    response = client.get(f"/api/v1/cash-register/{session_id}/statement/")

    assert response.status_code == 200, response.content
    assert response.json()["session"]["cash_station_name"] == "Caixa 1"
    statement_order = response.json()["orders"][0]
    assert response.json()["session"]["closed_by_name"] == ""
    assert statement_order["sequence"] == 91
    assert statement_order["items"][0]["id"] == str(item.pk)
    assert statement_order["items"][0]["product_name"] == "X-Burger"
