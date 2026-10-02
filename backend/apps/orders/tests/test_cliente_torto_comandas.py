"""Zerar e histórico de comandas contra o que um cliente com defeito manda.

Regra: corpo errado é 400, coisa que não existe é 404, estado que não deixa é
409 — nunca 500, e nada muda no banco quando a resposta é de erro. E zerar é
cancelamento em massa: quem não tem a permissão de cancelar precisa da senha
de operação ou do login de um supervisor.
"""
import uuid

import pytest
from rest_framework.test import APIClient

from apps.core.tenant import tenant_context
from apps.orders.command_items import launch_item
from apps.orders.models import CommandItem
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db

ZERAR = "/api/v1/commands/bulk-reset/"


@pytest.fixture
def comanda(contexto_tenant, account, restaurant, branch, manager_user, produto):
    cartao = Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=501)
    launch_item(command=cartao, product=produto, user=manager_user, quantity=1)
    return cartao


def _intacta(comanda):
    with tenant_context(comanda.account):
        return not CommandItem.objects.filter(command=comanda, status=CommandItem.STATUS_CANCELLED).exists()


@pytest.mark.parametrize("corpo", [
    {},
    {"ids": "abc", "reason": "x"},
    {"ids": {"a": 1}, "reason": "x"},
    {"ids": [], "reason": "x"},
    {"ids": [str(uuid.uuid4())] * 501, "reason": "x"},
])
def test_lista_de_ids_torta_e_400(api_client, comanda, corpo):
    assert api_client.post(ZERAR, corpo, format="json").status_code == 400
    assert _intacta(comanda)


@pytest.mark.parametrize("ids", [[None], ["nao-e-uuid"], [123], [""], [{"id": "x"}]])
def test_id_que_nao_e_uuid_volta_como_nao_encontrada(api_client, comanda, ids):
    resposta = api_client.post(ZERAR, {"ids": [str(comanda.pk), *ids], "reason": "Limpeza"}, format="json")

    assert resposta.status_code == 200, resposta.content
    assert [r["number"] for r in resposta.data["reset"]] == [501]
    assert all(r["reason"] == "Comanda não encontrada." for r in resposta.data["skipped"])


@pytest.mark.parametrize("motivo", [None, "", "   ", ["Limpeza"], {"m": "x"}])
def test_motivo_ausente_ou_que_nao_e_texto_e_400(api_client, comanda, motivo):
    resposta = api_client.post(ZERAR, {"ids": [str(comanda.pk)], "reason": motivo}, format="json")

    assert resposta.status_code == 400, resposta.content
    assert _intacta(comanda)


def test_corpo_em_lista_e_400(api_client, comanda):
    assert api_client.post(ZERAR, [str(comanda.pk)], format="json").status_code == 400
    assert _intacta(comanda)


def test_ids_repetidos_zeram_uma_vez(api_client, comanda):
    resposta = api_client.post(ZERAR, {"ids": [str(comanda.pk)] * 3, "reason": "Limpeza"}, format="json")

    assert resposta.data["reset"] == [{"id": str(comanda.pk), "number": 501, "items_removed": 1}]
    assert resposta.data["skipped"] == []


def test_sem_login_e_401_e_get_e_405(comanda):
    anonimo = APIClient()
    assert anonimo.post(ZERAR, {"ids": [str(comanda.pk)], "reason": "x"}, format="json").status_code == 401
    assert _intacta(comanda)


def test_get_no_endpoint_de_zerar_e_405(api_client, comanda):
    assert api_client.get(ZERAR).status_code == 405


@pytest.fixture
def garcom(account, restaurant, branch):
    from django.contrib.auth import get_user_model

    from apps.accounts.models import UserProfile
    from apps.accounts.role_catalog import CODE_WAITER
    from conftest import _authenticated_client, _role_for

    usuario = get_user_model().objects.create_user(username="garcom-zerar", password="x")
    UserProfile.objects.create(
        account=account, user=usuario, restaurant=restaurant, branch=branch, role=_role_for(account, CODE_WAITER),
    )
    return _authenticated_client(usuario)


def test_garcom_sem_autorizacao_nao_zera(garcom, comanda):
    resposta = garcom.post(ZERAR, {"ids": [str(comanda.pk)], "reason": "Limpeza"}, format="json")

    assert resposta.status_code == 200, resposta.content
    assert resposta.data["reset"] == []
    assert "senha de operação" in resposta.data["skipped"][0]["reason"]
    assert _intacta(comanda)


def test_garcom_com_a_senha_de_operacao_zera(garcom, comanda, restaurant):
    restaurant.set_cash_action_password("4321")
    restaurant.save()

    resposta = garcom.post(ZERAR, {"ids": [str(comanda.pk)], "reason": "Limpeza", "cash_password": 4321}, format="json")

    assert [r["number"] for r in resposta.data["reset"]] == [501]


@pytest.mark.parametrize("consulta", [
    "page=abc", "page=-1", "page=0", "page_size=0", "page_size=99999", "page_size=x",
    "after=2026-13-45", "before=ontem", "after=2026-10-02T10:00",
])
def test_historico_com_parametro_torto_nao_quebra(api_client, comanda, consulta):
    resposta = api_client.get(f"/api/v1/commands/{comanda.pk}/history/?{consulta}")

    assert resposta.status_code in (200, 400), resposta.content
    if resposta.status_code == 200:
        assert len(resposta.data["results"]) <= 200


@pytest.mark.parametrize("pk", [str(uuid.uuid4()), "nao-e-uuid"])
def test_historico_de_comanda_inexistente_e_404(api_client, comanda, pk):
    assert api_client.get(f"/api/v1/commands/{pk}/history/").status_code == 404
