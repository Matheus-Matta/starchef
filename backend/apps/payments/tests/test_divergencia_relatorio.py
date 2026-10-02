"""O relatório das sessões selecionadas na página de caixa."""
from decimal import Decimal

import pytest

from apps.payments.tests.conftest import RELATORIO, URL, corpo

pytestmark = pytest.mark.django_db


def _relatorio(cliente, *sessoes):
    resposta = cliente.get(RELATORIO, {"cash_registers": ",".join(str(s.pk) for s in sessoes)})
    assert resposta.status_code == 200, resposta.content
    return resposta.data


def _por_nome(formas):
    return {f["name"]: Decimal(f["amount"]) for f in formas}


def test_soma_o_registrado_e_a_divergencia_por_forma(api_client, sessao_de_caixa, forma, venda):
    """O exemplo do fechamento: R$ 15.000 no PDV, R$ 18.500 recebidos."""
    sessao, pix, cartao, dinheiro = sessao_de_caixa(), forma("PIX"), forma("Cartão", "card"), forma("Dinheiro", "cash")
    venda(sessao, pix, "7000.00")
    venda(sessao, cartao, "6000.00")
    venda(sessao, dinheiro, "2000.00")
    api_client.post(URL, corpo(sessao, (pix, "2000.00"), (cartao, "1000.00"), (dinheiro, "500.00")), format="json")

    linha = _relatorio(api_client, sessao)["sessions"][0]

    assert Decimal(linha["registered_sales"]) == Decimal("15000.00")
    assert Decimal(linha["discrepancy_total"]) == Decimal("3500.00")
    assert Decimal(linha["received_total"]) == Decimal("18500.00")
    assert _por_nome(linha["discrepancy_by_method"]) == {
        "Cartão": Decimal("1000.00"), "Dinheiro": Decimal("500.00"), "PIX": Decimal("2000.00"),
    }


def test_cancelada_aparece_mas_nao_soma(api_client, sessao_de_caixa, forma):
    sessao, pix = sessao_de_caixa(), forma("PIX")
    valida = api_client.post(URL, corpo(sessao, (pix, "100.00")), format="json").data
    errada = api_client.post(URL, corpo(sessao, (pix, "900.00")), format="json").data
    api_client.post(f"{URL}{errada['id']}/cancel/", {"reason": "Lançada em dobro."}, format="json")

    linha = _relatorio(api_client, sessao)["sessions"][0]

    assert Decimal(linha["discrepancy_total"]) == Decimal("100.00")
    assert {d["id"]: d["status"] for d in linha["discrepancies"]} == {
        valida["id"]: "open", errada["id"]: "cancelled",
    }


def test_totais_de_varias_sessoes(api_client, sessao_de_caixa, forma, venda):
    pix = forma("PIX")
    a, b = sessao_de_caixa(), sessao_de_caixa(station="Caixa 2")
    venda(a, pix, "10.00")
    venda(b, pix, "20.00")
    api_client.post(URL, corpo(a, (pix, "1.10")), format="json")
    api_client.post(URL, corpo(b, (pix, "2.20")), format="json")

    totais = _relatorio(api_client, a, b)["totals"]

    assert Decimal(totais["registered_sales"]) == Decimal("30.00")
    assert Decimal(totais["discrepancy_total"]) == Decimal("3.30")
    assert Decimal(totais["received_total"]) == Decimal("33.30")
    assert totais["open_count"] == 2


def test_pagamento_cancelado_nao_conta_como_venda(api_client, sessao_de_caixa, forma, venda):
    sessao, pix = sessao_de_caixa(), forma("PIX")
    venda(sessao, pix, "50.00")
    estornado = venda(sessao, pix, "70.00")
    estornado.status = "cancelled"
    estornado.save(update_fields=["status"])

    assert Decimal(_relatorio(api_client, sessao)["sessions"][0]["registered_sales"]) == Decimal("50.00")


def test_sessao_de_outra_conta_nao_aparece(api_client, sessao_de_caixa, admin_user):
    from apps.accounts.models import Account
    from apps.payments.models import CashRegister
    from apps.restaurants.models import Branch, Restaurant

    outra = Account.objects.create(name="Outra")
    loja = Restaurant.all_objects.create(account=outra, legal_name="O LTDA", trade_name="O")
    alheia = CashRegister.all_objects.create(
        account=outra, restaurant=loja, branch=Branch.all_objects.filter(restaurant=loja).first(),
        opened_by=admin_user, created_by=admin_user, updated_by=admin_user,
    )
    minha = sessao_de_caixa()

    sessoes = _relatorio(api_client, minha, alheia)["sessions"]

    assert [s["cash_register"] for s in sessoes] == [str(minha.pk)]


@pytest.mark.parametrize("consulta", ["", "nao-e-uuid", ",".join(["x"] * 101)], ids=["vazio", "torto", "demais"])
def test_selecao_invalida_e_400(api_client, consulta):
    assert api_client.get(RELATORIO, {"cash_registers": consulta}).status_code == 400


def test_operador_de_caixa_nao_ve_o_relatorio(caixa_client, sessao_de_caixa):
    assert caixa_client.get(RELATORIO, {"cash_registers": str(sessao_de_caixa().pk)}).status_code == 403


def test_consultas_nao_crescem_com_o_numero_de_sessoes(
    api_client, sessao_de_caixa, forma, venda, django_assert_max_num_queries
):
    """Ação em massa valida EM LOTE: 30 sessões custam o mesmo que 3."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    pix = forma("PIX")

    def medir(quantas):
        sessoes = [sessao_de_caixa(station=f"C{quantas}-{i}") for i in range(quantas)]
        for sessao in sessoes:
            venda(sessao, pix, "10.00")
            api_client.post(URL, corpo(sessao, (pix, "1.00")), format="json")
        with CaptureQueriesContext(connection) as capturadas:
            _relatorio(api_client, *sessoes)
        return len(capturadas)

    poucas, muitas = medir(3), medir(30)

    assert muitas == poucas, f"3 sessões: {poucas} consultas; 30 sessões: {muitas}"
