"""Desistir do que ficou esperando a senha: fechamento, sangria e suprimento.

O operador fecha o caixa, conta errado, cai em "divergência" — e a única saída
era a senha de ações do caixa ou sair do sistema. A mesma coisa na sangria:
digitou R$ 500 em vez de R$ 50 e ela ficou pendente, esperando um gerente
aprovar um valor que ninguém quer aprovar.

`cancel-pending` desfaz o gesto em vez de autorizá-lo: o fechamento volta a
ser caixa aberto (o operador conta de novo) e a movimentação vira cancelada,
fora do saldo. Não pede senha — não libera nada, só devolve ao estado de antes.

E o motivo da sangria/suprimento deixou de ser obrigatório: na gaveta, com fila
no caixa, o operador escrevia "." para passar.
"""
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.payments.models import CashMovement, CashRegister
from apps.payments.services import close_cash_register, create_cash_movement, open_cash_register

pytestmark = pytest.mark.django_db


@pytest.fixture
def sessao(account, restaurant, branch, manager_user):
    restaurant.cash_closing_tolerance = Decimal("0.00")
    restaurant.save(update_fields=["cash_closing_tolerance"])
    with tenant_context(account):
        return open_cash_register(
            restaurant=restaurant, branch=branch, user=manager_user, opening_amount=Decimal("100.00")
        )


def _cancelar(cliente, sessao, **corpo):
    return cliente.post(f"/api/v1/cash-register/{sessao.pk}/cancel-pending/", corpo, format="json")


def test_sangria_sem_motivo_e_aceita(api_client, sessao):
    resposta = api_client.post(
        f"/api/v1/cash-register/{sessao.pk}/withdrawal/", {"amount": "20.00", "reason": ""}, format="json"
    )

    assert resposta.status_code == 201, resposta.content
    assert resposta.json()["reason"] == ""


def test_sangria_sem_valor_continua_recusada(api_client, sessao):
    """Tirar a obrigação do motivo não pode levar junto a do valor."""
    resposta = api_client.post(
        f"/api/v1/cash-register/{sessao.pk}/withdrawal/", {"amount": "0", "reason": ""}, format="json"
    )

    assert resposta.status_code == 400, resposta.content


def test_cancelar_fechamento_divergente_devolve_o_caixa_aberto(api_client, sessao, manager_user):
    with tenant_context(sessao.account):
        close_cash_register(cash_register=sessao, user=manager_user, actual_amount=Decimal("80.00"))
    sessao.refresh_from_db()
    assert sessao.status == CashRegister.STATUS_PENDING_APPROVAL

    resposta = _cancelar(api_client, sessao)

    assert resposta.status_code == 200, resposta.content
    sessao.refresh_from_db()
    assert sessao.status == CashRegister.STATUS_OPEN
    assert sessao.pending_operation == ""
    assert sessao.actual_amount is None
    assert sessao.closed_by_id is None
    # O lançamento de fechamento sai do histórico ativo: o caixa não fechou.
    assert not CashMovement.all_objects.filter(
        cash_register=sessao, movement_type=CashMovement.TYPE_CLOSING, status="approved"
    ).exists()


def test_caixa_reaberto_pode_ser_fechado_de_novo(api_client, sessao, manager_user):
    with tenant_context(sessao.account):
        close_cash_register(cash_register=sessao, user=manager_user, actual_amount=Decimal("80.00"))
    _cancelar(api_client, sessao)

    with tenant_context(sessao.account):
        fechado = close_cash_register(cash_register=sessao, user=manager_user, actual_amount=Decimal("100.00"))

    assert fechado.status == CashRegister.STATUS_CLOSED


def test_cancelar_sangria_pendente_tira_ela_do_saldo(api_client, sessao, manager_user):
    with tenant_context(sessao.account):
        sangria = create_cash_movement(
            cash_register=sessao, user=manager_user, movement_type=CashMovement.TYPE_WITHDRAWAL,
            amount="500.00", reason="",
        )

    resposta = _cancelar(api_client, sessao, movement=str(sangria.pk))

    assert resposta.status_code == 200, resposta.content
    sangria.refresh_from_db()
    assert sangria.status == "cancelled"
    # Cancelada, ela não pode mais ser aprovada por engano depois.
    aprovar = api_client.post(
        f"/api/v1/cash-register/{sessao.pk}/approve/",
        {"movement": str(sangria.pk), "reason": "ok"},
        format="json",
    )
    assert aprovar.status_code in {400, 409}
    sangria.refresh_from_db()
    assert sangria.status == "cancelled"


def test_cancelar_sem_nada_pendente_e_conflito(api_client, sessao):
    """409, não 400: o PDV reenvia 400 para sempre, e aqui o problema é o ESTADO."""
    resposta = _cancelar(api_client, sessao)

    assert resposta.status_code == 409, resposta.content
    sessao.refresh_from_db()
    assert sessao.status == CashRegister.STATUS_OPEN
