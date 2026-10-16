"""O cartão da comanda mostra, de passagem, o que já foi lançado nela.

O app do garçom desenha a grade de comandas e só sabia QUANTOS itens cada uma
tinha. Para saber O QUE, ele abria o cartão — uma ida ao servidor por comanda.
Com `?preview=1` a listagem traz um resumo curto (nome do cadastro do produto
e quantidade), montado numa consulta só para a página inteira.
"""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.tenant import tenant_context
from apps.orders.command_items import launch_item
from apps.orders.models import CommandItem
from apps.restaurants import command_preview
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


def _comanda(restaurant, branch, numero):
    return Command.objects.create(
        account=restaurant.account, restaurant=restaurant, branch=branch,
        number=numero, code=f"RES-{numero:04d}",
    )


def _lista(cliente, extra="&preview=1"):
    resposta = cliente.get(f"/api/v1/commands/?page_size=100&is_active=true{extra}")
    assert resposta.status_code == 200, resposta.content
    return {linha["number"]: linha for linha in resposta.data["results"]}


def test_resumo_junta_o_mesmo_produto_e_ignora_cancelado(
    api_client, restaurant, branch, manager_user, produto, produto_barato,
):
    """Duas rodadas de X-Burger são "3x X-Burger", e não duas linhas; o item
    cancelado não é consumo e não aparece."""
    comanda = _comanda(restaurant, branch, 1)
    launch_item(command=comanda, product=produto, user=manager_user, quantity=2)
    launch_item(command=comanda, product=produto_barato, user=manager_user, quantity=1)
    launch_item(command=comanda, product=produto, user=manager_user, quantity=1)
    cancelado = launch_item(command=comanda, product=produto_barato, user=manager_user, quantity=5)
    with tenant_context(restaurant.account):
        CommandItem.objects.filter(pk=cancelado.pk).update(status=CommandItem.STATUS_CANCELLED)
    _comanda(restaurant, branch, 2)

    linhas = _lista(api_client)

    assert linhas[1]["pending_preview"] == {
        "items": [
            {"name": "X-Burger", "quantity": "3", "unit": "unit"},
            {"name": "Refrigerante", "quantity": "1", "unit": "unit"},
        ],
        "more": 0,
    }
    assert linhas[2]["pending_preview"] == {"items": [], "more": 0}


def test_resumo_corta_no_limite_e_conta_o_resto(
    api_client, restaurant, branch, manager_user, produto, produto_barato, monkeypatch,
):
    monkeypatch.setattr(command_preview, "LIMITE", 1)
    comanda = _comanda(restaurant, branch, 1)
    launch_item(command=comanda, product=produto, user=manager_user, quantity=1)
    launch_item(command=comanda, product=produto_barato, user=manager_user, quantity=1)

    resumo = _lista(api_client)[1]["pending_preview"]

    assert [item["name"] for item in resumo["items"]] == ["X-Burger"]
    assert resumo["more"] == 1


def test_sem_pedir_o_resumo_a_lista_nao_paga_por_ele(api_client, restaurant, branch, manager_user, produto):
    """O PDV e o painel não pedem: para eles o campo vem vazio, sem consulta."""
    launch_item(command=_comanda(restaurant, branch, 1), product=produto, user=manager_user, quantity=1)

    assert _lista(api_client, extra="")[1]["pending_preview"] is None


def test_resumo_custa_o_mesmo_com_2_ou_com_8_comandas(api_client, restaurant, branch, manager_user, produto):
    def cria(de, ate):
        for numero in range(de, ate):
            launch_item(command=_comanda(restaurant, branch, numero), product=produto, user=manager_user, quantity=1)

    cria(1, 3)
    with CaptureQueriesContext(connection) as com_dois:
        _lista(api_client)
    cria(3, 9)
    with CaptureQueriesContext(connection) as com_oito:
        _lista(api_client)

    assert len(com_oito) == len(com_dois), f"{len(com_dois)} consultas com 2, {len(com_oito)} com 8"


def test_cartao_relido_pelos_itens_traz_o_mesmo_resumo(api_client, restaurant, branch, manager_user, produto):
    """O app relê UM cartão por `/commands/{id}/items/` depois de lançar; sem o
    resumo ali, o cartão ficava mostrando o consumo de antes do lançamento."""
    comanda = _comanda(restaurant, branch, 1)
    launch_item(command=comanda, product=produto, user=manager_user, quantity=2)

    resposta = api_client.get(f"/api/v1/commands/{comanda.pk}/items/")

    assert resposta.status_code == 200, resposta.content
    assert resposta.data["command"]["pending_preview"]["items"] == [
        {"name": "X-Burger", "quantity": "2", "unit": "unit"}
    ]
