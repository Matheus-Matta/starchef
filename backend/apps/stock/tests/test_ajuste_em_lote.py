"""Ajuste de estoque em lote: entrada, saída ou novo saldo, com motivo.

Cada linha vira um movimento de "Ajuste de inventário" com o motivo e quem
fez — é a trilha de auditoria. Tudo numa transação: uma linha inválida não
deixa metade do lote aplicada.
"""
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.stock.models import StockMovement
from apps.stock.tests.test_stock_positions import (  # noqa: F401 — fixtures
    _ingredient,
    _movement,
    _tenant,
    account_with_logistica,
    location,
)

pytestmark = pytest.mark.django_db
ROTA = "/api/v1/stock/movements/bulk-adjust/"


@pytest.fixture
def insumos(account_with_logistica, restaurant, branch, manager_user, location):  # noqa: F811
    conta = account_with_logistica
    with tenant_context(conta):
        arroz = _ingredient(conta, restaurant, branch, manager_user, "Arroz", average_cost=Decimal("5"))
        feijao = _ingredient(conta, restaurant, branch, manager_user, "Feijão")
        oleo = _ingredient(conta, restaurant, branch, manager_user, "Óleo")
        _movement(conta, restaurant, branch, manager_user, location, arroz, "10")
        _movement(conta, restaurant, branch, manager_user, location, oleo, "4")
    return {"arroz": arroz, "feijao": feijao, "oleo": oleo}


def _saldo(account, ingrediente, local):
    with tenant_context(account):
        return sum(
            (m.quantity for m in StockMovement.objects.filter(ingredient=ingrediente, location=local)),
            Decimal("0"),
        )


def test_entrada_saida_e_novo_saldo_num_lote_so(api_client, account_with_logistica, location, insumos):  # noqa: F811
    resposta = api_client.post(ROTA, {
        "location": str(location.pk),
        "reason": "Inventário de fim de mês",
        "items": [
            {"ingredient": str(insumos["arroz"].pk), "mode": "set", "quantity": "7"},
            {"ingredient": str(insumos["feijao"].pk), "mode": "in", "quantity": "3"},
            {"ingredient": str(insumos["oleo"].pk), "mode": "out", "quantity": "1.5"},
        ],
    }, format="json")

    assert resposta.status_code == 201, resposta.data
    assert _saldo(account_with_logistica, insumos["arroz"], location) == Decimal("7")
    assert _saldo(account_with_logistica, insumos["feijao"], location) == Decimal("3")
    assert _saldo(account_with_logistica, insumos["oleo"], location) == Decimal("2.5")
    with tenant_context(account_with_logistica):
        ajuste = StockMovement.objects.get(ingredient=insumos["arroz"], movement_type=StockMovement.TYPE_INVENTORY_ADJUSTMENT_NEGATIVE)
    assert ajuste.quantity == Decimal("-3")
    assert ajuste.reason == "Inventário de fim de mês"
    assert ajuste.operator is not None
    assert ajuste.total_cost == Decimal("-15.00")


def test_sem_motivo_e_recusado_e_nada_e_gravado(api_client, account_with_logistica, location, insumos):  # noqa: F811
    resposta = api_client.post(ROTA, {
        "location": str(location.pk), "reason": "  ",
        "items": [{"ingredient": str(insumos["feijao"].pk), "mode": "in", "quantity": "3"}],
    }, format="json")

    assert resposta.status_code == 400
    assert _saldo(account_with_logistica, insumos["feijao"], location) == Decimal("0")


def test_linha_invalida_nao_deixa_metade_do_lote_aplicada(api_client, account_with_logistica, location, insumos):  # noqa: F811
    resposta = api_client.post(ROTA, {
        "location": str(location.pk), "reason": "Contagem",
        "items": [
            {"ingredient": str(insumos["feijao"].pk), "mode": "in", "quantity": "3"},
            {"ingredient": str(insumos["oleo"].pk), "mode": "out", "quantity": "-1"},
        ],
    }, format="json")

    assert resposta.status_code == 400
    assert _saldo(account_with_logistica, insumos["feijao"], location) == Decimal("0")


def test_novo_saldo_igual_ao_atual_nao_gera_movimento(api_client, account_with_logistica, location, insumos):  # noqa: F811
    resposta = api_client.post(ROTA, {
        "location": str(location.pk), "reason": "Conferência",
        "items": [{"ingredient": str(insumos["arroz"].pk), "mode": "set", "quantity": "10"}],
    }, format="json")

    assert resposta.status_code == 201, resposta.data
    assert resposta.data["created"] == 0
