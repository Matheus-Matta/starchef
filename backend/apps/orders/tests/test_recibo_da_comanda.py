"""O recibo (conferência) da comanda impresso pela tela de comandas.

Não saía: o texto ia em `payload["text"]` e o agente do PDV lê
`text_content` — o trabalho chegava vazio. E a impressora era a primeira por
nome, que podia ser a da cozinha. Agora sai como a etiqueta da balança (texto
+ código de barras da comanda), na impressora escolhida pelo terminal.
"""
import pytest

from apps.orders.command_items import launch_item
from apps.printers.models import Printer
from apps.restaurants.models import Command, TableSector

pytestmark = pytest.mark.django_db


@pytest.fixture
def comanda(contexto_tenant, account, restaurant, branch, manager_user, produto):
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=21)
    launch_item(command=comanda, product=produto, user=manager_user, quantity=2)
    return comanda


@pytest.fixture
def impressoras(account, restaurant, branch):
    base = {"account": account, "restaurant": restaurant, "branch": branch,
            "connection_type": "network", "driver_type": "escpos", "is_active": True}
    setor = TableSector.objects.create(account=account, restaurant=restaurant, branch=branch, name="Cozinha")
    cozinha = Printer.objects.create(name="A Cozinha", host="10.0.0.2", sector=setor, **base)
    caixa = Printer.objects.create(name="Caixa", host="10.0.0.3", **base)
    return cozinha, caixa


def test_recibo_sai_com_texto_e_codigo_de_barras_na_impressora_de_caixa(admin_client, comanda, impressoras):
    _, caixa = impressoras

    resposta = admin_client.post(f"/api/v1/commands/{comanda.id}/receipt/", {}, format="json")

    assert resposta.status_code == 201, resposta.json()
    dados = resposta.json()
    assert dados["printer"]["id"] == str(caixa.id)  # e não "A Cozinha", a primeira por nome
    assert "COMANDA 21" in dados["payload"]["text_content"]
    assert dados["payload"]["barcode"] == {"symbology": "CODE128", "value": comanda.code or "21"}


def test_recibo_vai_para_a_impressora_master_escolhida_no_terminal(admin_client, comanda, impressoras):
    cozinha, _ = impressoras

    resposta = admin_client.post(
        f"/api/v1/commands/{comanda.id}/receipt/",
        {"printer": str(cozinha.id), "manual_only": True},
        format="json",
    )

    assert resposta.status_code == 201, resposta.json()
    assert resposta.json()["printer"]["id"] == str(cozinha.id)
    assert resposta.json()["payload"]["manual_only"] is True
