"""O PDV acha a última abertura e o último fechamento DA ESTAÇÃO para reimprimir.

O filtro é `cash_station` (o caixa físico), não `station` (o rótulo livre):
dois caixas com o mesmo nome "PDV principal" traziam o papel do vizinho.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.payments.models import CashRegister, CashStation

pytestmark = pytest.mark.django_db


def _estacao(account, restaurant, admin_user, codigo):
    return CashStation.all_objects.create(
        account=account, restaurant=restaurant, name=codigo, code=codigo,
        created_by=admin_user, updated_by=admin_user)


def _sessao(account, restaurant, branch, admin_user, estacao, *, aberta_ha, fechada_ha=None):
    agora = timezone.now()
    sessao = CashRegister.all_objects.create(
        account=account, restaurant=restaurant, branch=branch, cash_station=estacao,
        opened_by=admin_user, opening_amount="10.00", expected_amount="10.00",
        status=CashRegister.STATUS_CLOSED if fechada_ha is not None else CashRegister.STATUS_OPEN,
        created_by=admin_user, updated_by=admin_user)
    CashRegister.all_objects.filter(pk=sessao.pk).update(
        opened_at=agora - timedelta(hours=aberta_ha),
        closed_at=agora - timedelta(hours=fechada_ha) if fechada_ha is not None else None)
    return sessao


def test_ultimo_fechamento_e_a_ultima_abertura_sao_da_estacao(
    admin_client, account, restaurant, branch, admin_user,
):
    minha = _estacao(account, restaurant, admin_user, "CX-1")
    vizinha = _estacao(account, restaurant, admin_user, "CX-2")
    fechada_antes = _sessao(account, restaurant, branch, admin_user, minha, aberta_ha=30, fechada_ha=20)
    fechada_por_ultimo = _sessao(account, restaurant, branch, admin_user, minha, aberta_ha=10, fechada_ha=2)
    aberta_agora = _sessao(account, restaurant, branch, admin_user, minha, aberta_ha=1)
    _sessao(account, restaurant, branch, admin_user, vizinha, aberta_ha=0.5, fechada_ha=0.1)

    fechamento = admin_client.get("/api/v1/cash-register/", {
        "cash_station": str(minha.id), "status": "closed", "ordering": "-closed_at", "page_size": 1,
    }).json()["results"]
    abertura = admin_client.get("/api/v1/cash-register/", {
        "cash_station": str(minha.id), "ordering": "-opened_at", "page_size": 1,
    }).json()["results"]

    assert [s["id"] for s in fechamento] == [str(fechada_por_ultimo.id)]
    assert [s["id"] for s in abertura] == [str(aberta_agora.id)]
    assert str(fechada_antes.id) not in {s["id"] for s in fechamento + abertura}
