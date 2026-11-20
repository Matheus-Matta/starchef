"""Os totais de ICMS/PIS/COFINS da NFC-e são a soma dos itens.

Produção, 20/11/2026, primeira venda em Regime Normal: "602 Rejeicao: Total do
PIS difere do somatorio dos itens sujeitos ao ICMS". A seção `[Total]` do INI
não levava vPIS/vCOFINS/vBC/vICMS, e a ACBrLib os gravava zerados.
"""
from apps.invoices.acbrlib.ini_impostos import icms, totais
from apps.invoices.tests.test_acbrlib_provider import ambiente  # noqa: F401

PRATO = {"icms_origem": "0", "icms_situacao_tributaria": "00", "icms_aliquota": "12.00",
         "icms_base_calculo": "50.00", "icms_valor": "6.00", "pis_valor": "0.33",
         "cofins_valor": "1.50"}
REFRI_ST = {"icms_origem": "0", "icms_situacao_tributaria": "60", "icms_aliquota": "12.00",
            "icms_base_calculo": "10.00", "icms_valor": "1.20", "pis_valor": "0.00",
            "cofins_valor": "0.00"}
CAFE = {**PRATO, "icms_base_calculo": "7.00", "icms_valor": "0.84", "pis_valor": "0.05",
        "cofins_valor": "0.21"}


def test_total_do_pis_e_do_cofins_e_a_soma_dos_itens():
    total = totais([PRATO, CAFE, REFRI_ST], simples=False)

    assert total["vPIS"] == "0.38"
    assert total["vCOFINS"] == "1.71"


def test_total_do_icms_so_soma_o_cst_que_destaca_icms():
    """O CST 60 (ST já recolhida) não tem vICMS no item: no total também não."""
    total = totais([PRATO, CAFE, REFRI_ST], simples=False)

    assert total["vBC"] == "57.00"
    assert total["vICMS"] == "6.84"


def test_cst_60_nao_leva_aliquota_nem_valor_de_icms_no_item():
    assert icms(REFRI_ST, simples=False) == {"orig": "0", "CST": "60"}


def test_cst_00_leva_base_aliquota_valor_e_a_modalidade_da_base():
    campos = icms(PRATO, simples=False)

    assert campos["modBC"] == "3"
    assert (campos["vBC"], campos["pICMS"], campos["vICMS"]) == ("50.00", "12.00", "6.00")


def test_no_simples_os_totais_de_icms_seguem_zerados():
    item = {**PRATO, "icms_situacao_tributaria": "102"}

    total = totais([item], simples=True)

    assert (total["vBC"], total["vICMS"]) == ("0.00", "0.00")
    assert icms(item, simples=True) == {"orig": "0", "CSOSN": "102"}


def test_nota_do_regime_normal_sai_com_os_totais_no_ini(ambiente, monkeypatch):  # noqa: F811
    """Caminho inteiro: X-Burger de R$ 25,00 com ICMS 12%, PIS 0,65% e COFINS 3%."""
    from apps.invoices.models import FiscalConfig, FiscalProfile
    from apps.invoices.services import emit_fiscal_invoice
    from apps.invoices.tests.test_acbrlib_provider import Comunicador
    from apps.orders.models import OrderItem

    perfil = FiscalProfile.objects.create(
        account=ambiente.pedido.account, name="PRATO", ncm="21069090", cfop="5102",
        cst_icms="00", icms_rate=12, pis_cst="01", pis_rate="0.65", cofins_cst="01", cofins_rate=3)
    produto = OrderItem.all_objects.filter(order=ambiente.pedido).first().product
    produto.fiscal_profile = perfil
    produto.save(update_fields=["fiscal_profile"])
    ambiente.config.crt = FiscalConfig.CRT_NORMAL
    ambiente.config.save(update_fields=["crt"])
    comunicador = Comunicador("online")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)

    emit_fiscal_invoice(ambiente.pedido, user=ambiente.user)

    total = comunicador.chamadas[0][1]["ini"].split("[Total]")[1].split("\n\n")[0]
    assert "vBC=25.00" in total and "vICMS=3.00" in total
    assert "vPIS=0.16" in total and "vCOFINS=0.75" in total
