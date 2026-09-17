"""Administrative recovery for a cash session tied to an unavailable terminal."""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import AuditLog
from apps.payments.models import CashMovement, CashRegister, CashStation

pytestmark = pytest.mark.django_db

OLD_TERMINAL = "11111111-1111-4111-8111-111111111111"
NEW_TERMINAL = "22222222-2222-4222-8222-222222222222"


def client_for(user, terminal_id=""):
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}",
        **({"HTTP_X_TERMINAL_ID": terminal_id} if terminal_id else {}),
    )
    return client


@pytest.fixture
def station(account, restaurant, manager_user):
    station = CashStation.objects.create(
        account=account,
        restaurant=restaurant,
        name="Caixa Principal",
        code="CX01",
    )
    station.operators.add(manager_user)
    return station


def open_session(station, manager_user):
    response = client_for(manager_user, OLD_TERMINAL).post(
        "/api/v1/cash-register/open/",
        {
            "cash_station": str(station.pk),
            "opening_amount": "100.00",
            "terminal_name": "Maquina antiga",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()["id"]


def test_admin_force_releases_session_and_new_terminal_can_open(
    station, manager_user, admin_user
):
    session_id = open_session(station, manager_user)
    pending = client_for(manager_user, OLD_TERMINAL).post(
        f"/api/v1/cash-register/{session_id}/supply/",
        {"amount": "20.00", "reason": "Troco adicional"},
        format="json",
    )
    assert pending.status_code == 201, pending.content

    response = client_for(admin_user, NEW_TERMINAL).post(
        f"/api/v1/cash-register/{session_id}/force-release/",
        {"reason": "O computador antigo parou de funcionar."},
        format="json",
    )

    assert response.status_code == 200, response.content
    session = CashRegister.all_objects.get(pk=session_id)
    assert session.status == CashRegister.STATUS_CANCELLED
    assert session.closed_by_id == admin_user.pk
    assert session.closed_at is not None
    assert session.actual_amount is None
    assert session.opened_terminal_label == "Maquina antiga"
    assert CashMovement.all_objects.get(pk=pending.json()["id"]).status == "cancelled"

    audit = AuditLog.all_objects.get(
        entity="CashRegister",
        object_id=str(session_id),
        metadata__event="cash_session_force_released",
    )
    assert audit.actor_id == admin_user.pk
    assert audit.reason == "O computador antigo parou de funcionar."

    reopened = client_for(manager_user, NEW_TERMINAL).post(
        "/api/v1/cash-register/open/",
        {
            "cash_station": str(station.pk),
            "opening_amount": "100.00",
            "terminal_name": "Maquina nova",
        },
        format="json",
    )
    assert reopened.status_code == 201, reopened.content


def test_manager_cannot_force_release(station, manager_user):
    session_id = open_session(station, manager_user)

    response = client_for(manager_user, NEW_TERMINAL).post(
        f"/api/v1/cash-register/{session_id}/force-release/",
        {"reason": "Tentativa sem privilegio de administrador."},
        format="json",
    )

    assert response.status_code == 403, response.content
    assert CashRegister.all_objects.get(pk=session_id).status == CashRegister.STATUS_OPEN


def test_force_release_requires_reason(station, manager_user, admin_user):
    session_id = open_session(station, manager_user)

    response = client_for(admin_user).post(
        f"/api/v1/cash-register/{session_id}/force-release/",
        {"reason": "   "},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert CashRegister.all_objects.get(pk=session_id).status == CashRegister.STATUS_OPEN
