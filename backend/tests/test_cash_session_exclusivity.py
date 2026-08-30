"""O Caixa Principal como autoridade unica da sessao.

Regra coberta aqui, para cada caixa cadastrado:

1. so uma sessao nao finalizada pode existir;
2. a sessao pertence a quem abriu e ao terminal onde foi aberta;
3. outro usuario nao assume, nao movimenta e nao fecha;
4. o mesmo usuario, no mesmo terminal, recupera depois de reiniciar/relogar;
5. o mesmo usuario em outra maquina tambem e bloqueado;
6. troca de operador/maquina so por transferencia gerencial, com justificativa;
7. logout nao fecha o caixa.
"""
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import AuditLog
from apps.payments.models import CashRegister, CashStation, PdvTerminal
from apps.payments.services import open_cash_register
from apps.payments.terminals import active_session_for_station

pytestmark = pytest.mark.django_db

BALCAO_01 = "11111111-1111-4111-8111-111111111111"
BALCAO_02 = "22222222-2222-4222-8222-222222222222"


# O middleware de tenant limpa a conta do contexto ao fim de cada request, e o
# manager padrao filtra justamente por ela: depois de uma chamada a API as
# asserçoes precisam ler pelo `all_objects`.
def sessions():
    return CashRegister.all_objects


def terminals():
    return PdvTerminal.all_objects


def client_for(user, installation_id=""):
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}",
        **({"HTTP_X_TERMINAL_ID": installation_id} if installation_id else {}),
    )
    return client


@pytest.fixture
def station(account, restaurant, manager_user, waiter_user):
    station = CashStation.objects.create(
        account=account, restaurant=restaurant, name="Caixa Principal", code="CX01"
    )
    station.operators.add(manager_user, waiter_user)
    return station


def open_via_api(client, station, *, installation_id=BALCAO_01, name="Balcão 01", amount="100.00"):
    return client.post(
        "/api/v1/cash-register/open/",
        {
            "cash_station": str(station.id),
            "opening_amount": amount,
            "terminal_installation_id": installation_id,
            "terminal_name": name,
            "terminal_type": "desktop",
            "terminal_role": "principal",
        },
        format="json",
    )


# ── 1 e 2: uma sessao por caixa, com dono e terminal ────────────────────


def test_open_registers_the_terminal_and_the_owner(station, manager_user):
    response = open_via_api(client_for(manager_user, BALCAO_01), station)

    assert response.status_code == 201, response.content
    session = sessions().get(pk=response.json()["id"])
    terminal = terminals().get(installation_id=BALCAO_01)
    assert session.opened_by_id == manager_user.pk
    assert session.opened_terminal_id == terminal.pk
    # Retrato do nome: renomear o terminal depois nao pode reescrever a auditoria.
    assert session.opened_terminal_label == "Balcão 01"
    assert terminal.name == "Balcão 01"
    assert terminal.role == PdvTerminal.ROLE_PRINCIPAL


def test_station_session_lock_targets_only_cash_register(station):
    """Nao tenta aplicar FOR UPDATE aos LEFT JOINs opcionais no PostgreSQL."""
    captured = {}

    def capture_first(queryset):
        captured["select_for_update"] = queryset.query.select_for_update
        captured["select_for_update_of"] = queryset.query.select_for_update_of
        return None

    with patch("django.db.models.query.QuerySet.first", capture_first):
        active_session_for_station(station, for_update=True)

    assert captured == {
        "select_for_update": True,
        "select_for_update_of": ("self",),
    }


def test_second_user_cannot_open_the_same_station(station, manager_user, waiter_user):
    open_via_api(client_for(manager_user, BALCAO_01), station)

    response = open_via_api(
        client_for(waiter_user, BALCAO_02), station, installation_id=BALCAO_02, name="Balcão 02"
    )

    assert response.status_code == 409, response.content
    body = response.json()
    assert body["code"] == "cash_session_conflict"
    assert "Caixa Principal" in body["message"]
    assert "Balcão 01" in body["message"]
    assert "transferência gerencial" in body["message"]
    assert body["session"]["opened_terminal_label"] == "Balcão 01"
    assert sessions().filter(cash_station=station).count() == 1


def test_database_refuses_a_second_active_session_for_the_station(station, manager_user, waiter_user):
    """A trava real: mesmo contornando o servico, o banco recusa.

    "Consulta e depois cria" nao resiste a duas aberturas simultaneas — as duas
    leem "livre" antes de qualquer uma gravar. O indice parcial e quem decide.
    """
    open_cash_register(restaurant=station.restaurant, cash_station=station, user=manager_user)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CashRegister.objects.create(
                account=station.account,
                restaurant=station.restaurant,
                cash_station=station,
                opened_by=waiter_user,
                station=station.name,
                status=CashRegister.STATUS_OPEN,
            )


def test_a_race_that_escapes_the_lock_becomes_409_not_500(station, manager_user, waiter_user):
    """Se a corrida chegar ao INSERT, a resposta ainda precisa ser um conflito.

    Simula a janela entre a consulta e a gravacao fingindo que o caixa estava
    livre; quem recusa e a `UniqueConstraint`, e a view traduz isso.
    """
    open_cash_register(restaurant=station.restaurant, cash_station=station, user=manager_user)

    with patch("apps.payments.services.active_session_for_station", return_value=None):
        response = open_via_api(
            client_for(waiter_user, BALCAO_02), station, installation_id=BALCAO_02, name="Balcão 02"
        )

    assert response.status_code == 409, response.content
    assert "Caixa Principal" in response.json()["message"]


def test_operator_cannot_hold_two_stations(account, restaurant, station, manager_user):
    other = CashStation.objects.create(
        account=account, restaurant=restaurant, name="Caixa 2", code="CX02"
    )
    other.operators.add(manager_user)
    open_via_api(client_for(manager_user, BALCAO_01), station)

    response = open_via_api(
        client_for(manager_user, BALCAO_02), other, installation_id=BALCAO_02, name="Balcão 02"
    )

    assert response.status_code == 409, response.content
    assert "já possui uma sessão" in response.json()["message"]


# ── 3: outro usuario nao assume, nao movimenta e nao fecha ──────────────


def test_another_operator_cannot_resume_move_or_close(station, manager_user, waiter_user):
    opened = open_via_api(client_for(manager_user, BALCAO_01), station).json()
    intruder = client_for(waiter_user, BALCAO_02)

    resumed = intruder.get("/api/v1/cash-register/current/")
    assert resumed.status_code == 409, resumed.content

    withdrawal = intruder.post(
        f"/api/v1/cash-register/{opened['id']}/withdrawal/",
        {"amount": "10.00", "reason": "teste", "terminal_installation_id": BALCAO_02},
        format="json",
    )
    assert withdrawal.status_code == 403, withdrawal.content

    supply = intruder.post(
        f"/api/v1/cash-register/{opened['id']}/supply/",
        {"amount": "10.00", "reason": "teste", "terminal_installation_id": BALCAO_02},
        format="json",
    )
    assert supply.status_code == 403, supply.content

    closed = intruder.post(
        f"/api/v1/cash-register/{opened['id']}/close/",
        {"actual_amount": "100.00", "terminal_installation_id": BALCAO_02},
        format="json",
    )
    assert closed.status_code == 403, closed.content
    assert sessions().get(pk=opened["id"]).status == CashRegister.STATUS_OPEN


# ── 4 e 7: recuperar apos reiniciar/relogar; logout nao fecha ───────────


def test_same_user_same_terminal_recovers_after_relogin(station, manager_user):
    opened = open_via_api(client_for(manager_user, BALCAO_01), station).json()

    # Sessao HTTP nova (equivale a reiniciar o terminal e logar de novo).
    recovered = client_for(manager_user, BALCAO_01).get("/api/v1/cash-register/current/")

    assert recovered.status_code == 200, recovered.content
    assert recovered.json()["id"] == opened["id"]
    assert recovered.json()["status"] == CashRegister.STATUS_OPEN
    assert recovered.json()["terminal_label"] == "Balcão 01"


def test_owner_closes_from_the_same_terminal(station, manager_user):
    opened = open_via_api(client_for(manager_user, BALCAO_01), station).json()

    response = client_for(manager_user, BALCAO_01).post(
        f"/api/v1/cash-register/{opened['id']}/close/",
        {"actual_amount": "100.00", "terminal_installation_id": BALCAO_01},
        format="json",
    )

    assert response.status_code == 200, response.content
    session = sessions().get(pk=opened["id"])
    assert session.status == CashRegister.STATUS_CLOSED
    assert session.closed_terminal_label == "Balcão 01"
    # Caixa livre de novo: a constraint parcial so vale para sessoes ativas.
    assert open_via_api(client_for(manager_user, BALCAO_01), station).status_code == 201


# ── 5: o mesmo usuario em outra maquina tambem e bloqueado ──────────────


def test_same_user_on_another_machine_is_blocked(station, manager_user):
    opened = open_via_api(client_for(manager_user, BALCAO_01), station).json()
    elsewhere = client_for(manager_user, BALCAO_02)

    resumed = elsewhere.get("/api/v1/cash-register/current/")
    assert resumed.status_code == 403, resumed.content
    assert resumed.json()["code"] == "cash_session_other_terminal"
    assert "Balcão 01" in resumed.json()["message"]

    closed = elsewhere.post(
        f"/api/v1/cash-register/{opened['id']}/close/",
        {"actual_amount": "100.00", "terminal_installation_id": BALCAO_02},
        format="json",
    )
    assert closed.status_code == 403, closed.content


def test_omitting_the_terminal_does_not_bypass_the_machine_rule(station, manager_user):
    """Nao mandar o identificador nao pode ser o atalho para contornar a regra."""
    opened = open_via_api(client_for(manager_user, BALCAO_01), station).json()

    response = client_for(manager_user).post(
        f"/api/v1/cash-register/{opened['id']}/close/", {"actual_amount": "100.00"}, format="json"
    )

    assert response.status_code == 403, response.content


# ── 6: transferencia gerencial ─────────────────────────────────────────


def test_manager_transfers_session_to_another_operator_and_terminal(
    station, manager_user, waiter_user, admin_user
):
    opened = open_via_api(client_for(manager_user, BALCAO_01), station).json()

    response = client_for(admin_user, BALCAO_02).post(
        f"/api/v1/cash-register/{opened['id']}/transfer/",
        {
            "reason": "Computador do Balcão 01 queimou",
            "new_operator": str(waiter_user.pk),
            "terminal_installation_id": BALCAO_02,
            "terminal_name": "Balcão 02",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    session = sessions().get(pk=opened["id"])
    assert session.opened_by_id == waiter_user.pk
    assert session.opened_terminal_label == "Balcão 02"

    # O novo dono opera; o antigo perde o acesso.
    assert (
        client_for(waiter_user, BALCAO_02).get("/api/v1/cash-register/current/").status_code == 200
    )
    assert (
        client_for(manager_user, BALCAO_01).get("/api/v1/cash-register/current/").status_code == 409
    )

    log = AuditLog.all_objects.filter(
        entity="CashRegister", metadata__event="cash_session_transferred"
    ).first()
    assert log is not None
    assert log.reason == "Computador do Balcão 01 queimou"
    assert log.metadata["previous_terminal"] == "Balcão 01"
    assert log.metadata["new_terminal"] == "Balcão 02"
    assert log.actor_id == admin_user.pk


def test_transfer_requires_a_reason(station, manager_user, admin_user):
    opened = open_via_api(client_for(manager_user, BALCAO_01), station).json()

    response = client_for(admin_user, BALCAO_02).post(
        f"/api/v1/cash-register/{opened['id']}/transfer/", {"reason": "   "}, format="json"
    )

    assert response.status_code == 400, response.content
    assert sessions().get(pk=opened["id"]).opened_by_id == manager_user.pk


def test_transfer_is_not_available_to_the_operator_who_wants_the_session(
    station, manager_user, waiter_user
):
    """Sem gerente nem senha do caixa, quem quer assumir nao se autoriza sozinho."""
    opened = open_via_api(client_for(manager_user, BALCAO_01), station).json()

    response = client_for(waiter_user, BALCAO_02).post(
        f"/api/v1/cash-register/{opened['id']}/transfer/",
        {"reason": "Quero usar este caixa", "new_operator": str(waiter_user.pk)},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert sessions().get(pk=opened["id"]).opened_by_id == manager_user.pk


def test_transfer_with_the_restaurant_cash_password(station, restaurant, manager_user, waiter_user):
    """Sem outro gerente presente, a senha de ações do caixa autoriza."""
    restaurant.set_cash_action_password("1234")
    restaurant.save(update_fields=["cash_action_password"])
    opened = open_via_api(client_for(manager_user, BALCAO_01), station).json()

    response = client_for(waiter_user, BALCAO_02).post(
        f"/api/v1/cash-register/{opened['id']}/transfer/",
        {
            "reason": "Operador foi embora sem fechar",
            "new_operator": str(waiter_user.pk),
            "cash_password": "1234",
            "terminal_installation_id": BALCAO_02,
            "terminal_name": "Balcão 02",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    assert sessions().get(pk=opened["id"]).opened_by_id == waiter_user.pk


def test_transfer_refuses_an_operator_who_already_holds_another_station(
    account, restaurant, station, manager_user, waiter_user, admin_user
):
    other = CashStation.objects.create(account=account, restaurant=restaurant, name="Caixa 2", code="CX02")
    other.operators.add(waiter_user)
    opened = open_via_api(client_for(manager_user, BALCAO_01), station).json()
    open_via_api(client_for(waiter_user, BALCAO_02), other, installation_id=BALCAO_02, name="Balcão 02")

    response = client_for(admin_user, BALCAO_02).post(
        f"/api/v1/cash-register/{opened['id']}/transfer/",
        {"reason": "Trocar operador", "new_operator": str(waiter_user.pk)},
        format="json",
    )

    assert response.status_code == 409, response.content
    assert sessions().get(pk=opened["id"]).opened_by_id == manager_user.pk


# ── terminal ───────────────────────────────────────────────────────────


def test_renaming_a_terminal_does_not_rewrite_past_sessions(station, manager_user):
    opened = open_via_api(client_for(manager_user, BALCAO_01), station).json()
    terminal = terminals().get(installation_id=BALCAO_01)
    terminal.name = "Balcão 07"
    terminal.save(update_fields=["name"])

    session = sessions().get(pk=opened["id"])
    assert session.opened_terminal_label == "Balcão 01"


def test_the_same_installation_is_never_registered_twice(station, manager_user):
    open_via_api(client_for(manager_user, BALCAO_01), station)
    session_id = sessions().get(cash_station=station).pk
    client_for(manager_user, BALCAO_01).post(
        f"/api/v1/cash-register/{session_id}/supply/",
        {"amount": "5.00", "reason": "troco", "terminal_installation_id": BALCAO_01},
        format="json",
    )

    assert terminals().filter(installation_id=BALCAO_01).count() == 1
    assert terminals().get(installation_id=BALCAO_01).last_seen_at is not None


# ── o recebimento tambem exige o dono ──────────────────────────────────


def test_payment_from_another_terminal_is_refused(
    station, restaurant, branch, table, product, manager_user
):
    """O dinheiro entra na gaveta de UM terminal.

    Bloquear so o botao de abrir nao impediria o recebimento de ser lancado de
    outra maquina — e ele soma ao saldo esperado da sessao, que e justamente o
    numero conferido as cegas no fechamento.
    """
    from apps.orders.models import Order
    from apps.orders.services import add_order_item, close_order, create_order
    from apps.payments.models import PaymentMethod

    opened = open_via_api(client_for(manager_user, BALCAO_01), station).json()
    cash = PaymentMethod.objects.create(
        account=station.account,
        restaurant=restaurant,
        branch=branch,
        name="Dinheiro do teste",
        method_type=PaymentMethod.TYPE_CASH,
    )
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_TABLE,
        table=table,
        user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    order = close_order(order, manager_user)

    payload = {
        "payment_method": str(cash.id),
        "amount": str(order.total),
        "cash_register": opened["id"],
    }
    elsewhere = client_for(manager_user, BALCAO_02).post(
        f"/api/v1/orders/{order.id}/pay/", payload, format="json"
    )
    assert elsewhere.status_code == 403, elsewhere.content

    owner = client_for(manager_user, BALCAO_01).post(
        f"/api/v1/orders/{order.id}/pay/", payload, format="json"
    )
    assert owner.status_code == 201, owner.content
