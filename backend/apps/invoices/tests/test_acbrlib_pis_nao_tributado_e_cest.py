"""PIS/COFINS não tributado fora do total, e CEST/NCM com o zero do Excel.

Produção, 21/11/2026, regime normal, mesmo depois da 3.1.21:

* "602 Rejeicao: Total do PIS difere do somatorio dos itens sujeitos ao ICMS".
  O refrigerante tem PIS CST 04 (monofásico) e o perfil tinha alíquota. O valor
  era calculado e somado na `[Total]`, mas o grupo PISNT (CST 04 a 09) não tem
  `vPIS`: a ACBrLib o descarta no item e o total ficava maior que a soma.
* "CEST ... The value '300504' is not accepted by the pattern '[0-9]{7}'". O
  CEST 03.005.04 passou pelo Excel e perdeu o zero, como o CST antes dele.
"""
import pytest

from apps.invoices.acbrlib.ini import _tributo
from apps.invoices.acbrlib.ini_impostos import totais
from apps.invoices.serializers import FiscalProfileSerializer
from apps.invoices.tests.test_acbrlib_provider import ambiente  # noqa: F401

PRATO = {"icms_situacao_tributaria": "00", "pis_situacao_tributaria": "01",
         "pis_valor": "0.33", "cofins_situacao_tributaria": "01", "cofins_valor": "1.50"}
REFRI = {"icms_situacao_tributaria": "60", "pis_situacao_tributaria": "04",
         "pis_valor": "0.10", "pis_base_calculo": "6.00", "pis_aliquota_porcentual": "1.65",
         "cofins_situacao_tributaria": "04", "cofins_valor": "0.46"}


def test_pis_e_cofins_monofasico_nao_entram_no_total():
    total = totais([PRATO, REFRI], simples=False)

    assert (total["vPIS"], total["vCOFINS"]) == ("0.33", "1.50")


def test_pis_monofasico_vai_ao_ini_so_com_o_cst():
    """O grupo PISNT só tem CST: mandar valor faria o item divergir do total."""
    assert _tributo(REFRI, "pis", "pPIS", "vPIS") == {"CST": "04"}


def test_pis_tributado_continua_com_o_valor():
    assert _tributo(PRATO, "pis", "pPIS", "vPIS") == {"CST": "01", "vPIS": "0.33"}


@pytest.mark.django_db
def test_importar_a_planilha_devolve_o_zero_do_cest_e_do_ncm(account):
    dados = {"name": "REFRIGERANTE_LATA_ST", "ncm": "9012100", "cest": "300504",
             "cfop": "5405", "cst_icms": "60", "csosn": ""}
    serializer = FiscalProfileSerializer(data=dados)
    serializer.is_valid(raise_exception=True)

    assert serializer.validated_data["cest"] == "0300504"
    assert serializer.validated_data["ncm"] == "09012100"


def test_perfil_gravado_sem_o_zero_sai_no_ini_com_cest_de_7_digitos(ambiente, monkeypatch):  # noqa: F811
    from apps.invoices.models import FiscalConfig, FiscalProfile
    from apps.invoices.services import emit_fiscal_invoice
    from apps.invoices.tests.test_acbrlib_provider import Comunicador
    from apps.orders.models import OrderItem

    perfil = FiscalProfile.objects.create(
        account=ambiente.pedido.account, name="REFRI", ncm="22021000", cest="300504",
        cfop="5405", cst_icms="60", pis_cst="04", pis_rate="1.65", cofins_cst="04",
        cofins_rate="7.60")
    produto = OrderItem.all_objects.filter(order=ambiente.pedido).first().product
    produto.fiscal_profile = perfil
    produto.save(update_fields=["fiscal_profile"])
    ambiente.config.crt = FiscalConfig.CRT_NORMAL
    ambiente.config.save(update_fields=["crt"])
    comunicador = Comunicador("online")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)

    emit_fiscal_invoice(ambiente.pedido, user=ambiente.user)

    texto = comunicador.chamadas[0][1]["ini"]
    assert "CEST=0300504" in texto
    total = texto.split("[Total]")[1].split("\n\n")[0]
    assert "vPIS=0.00" in total and "vCOFINS=0.00" in total
