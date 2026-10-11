"""A nota da ACBrLib sai com os dados fiscais DO RESTAURANTE que vendeu.

Na Focus o emitente já está cadastrado no painel dela: basta o CNPJ. Na
ACBrLib o XML inteiro nasce aqui, e o `FiscalConfig` só copiava o cadastro do
restaurante quando era criado — endereço preenchido depois, no restaurante,
nunca chegava à nota, e a SEFAZ recusava por falta de bairro ou CEP.
"""
import pytest

from apps.invoices.acbrlib.provider import AcbrLibProvider
from apps.invoices.models import Invoice
from apps.invoices.tests.test_acbrlib_provider import _emitir, ambiente  # noqa: F401

pytestmark = pytest.mark.django_db


def _emitente(ini):
    secao = ini.split("[Emitente]")[1].split("\n\n")[0]
    return dict(linha.split("=", 1) for linha in secao.strip().splitlines())


def _completa(config, **campos):
    valores = {"ie": "111222333444", "corporate_name": "Config LTDA", "trade_name": "Config",
               "address_line": "Rua da Config", "address_number": "10", "district": "Centro",
               "city": "São Paulo", "city_ibge": "3550308", "uf": "SP", "zip_code": "01001000"}
    valores.update(campos)
    for campo, valor in valores.items():
        setattr(config, campo, valor)
    config.save()


def test_campo_vazio_no_cadastro_fiscal_vem_do_restaurante(ambiente, monkeypatch):  # noqa: F811
    _completa(ambiente.config, address_line="", district="", zip_code="")
    restaurante = ambiente.pedido.restaurant
    restaurante.address, restaurante.district, restaurante.zip_code = (
        "Av. do Restaurante", "Vila Nova", "04001-000")
    restaurante.save()

    nota, comunicador = _emitir(ambiente, monkeypatch, "online")

    emitente = _emitente(comunicador.chamadas[0][1]["ini"])
    assert nota.status == Invoice.STATUS_ISSUED
    assert emitente["xLgr"] == "Av. do Restaurante"
    assert emitente["xBairro"] == "Vila Nova"
    assert emitente["CEP"] == "04001000"


def test_o_que_o_cadastro_fiscal_tem_continua_valendo(ambiente, monkeypatch):  # noqa: F811
    """A página fiscal ajusta a razão social; o cadastro do restaurante não a desfaz."""
    _completa(ambiente.config)
    restaurante = ambiente.pedido.restaurant
    restaurante.address = "Outro endereço"
    restaurante.save()

    _nota, comunicador = _emitir(ambiente, monkeypatch, "online")

    emitente = _emitente(comunicador.chamadas[0][1]["ini"])
    assert emitente["xLgr"] == "Rua da Config"
    assert emitente["xNome"] == "Config LTDA"
    assert emitente["CNPJCPF"] == "11222333000181"


def test_falta_de_dado_do_emitente_e_dita_antes_da_sefaz(ambiente):  # noqa: F811
    _completa(ambiente.config, city_ibge="", ie="")

    motivo = AcbrLibProvider().unavailable_reason(ambiente.config)

    assert motivo is not None
    assert "IBGE" in motivo and "Inscrição Estadual" in motivo


def test_emitir_sem_dado_do_emitente_nao_chama_a_sefaz_e_grava_o_motivo(ambiente, monkeypatch):  # noqa: F811
    """Antes ia ao comunicador e voltava recusada pelo schema, com a mensagem
    técnica da ACBrLib. O operador precisa do NOME do campo para corrigir."""
    _completa(ambiente.config, city_ibge="")

    nota, comunicador = _emitir(ambiente, monkeypatch, "online")

    assert comunicador.chamadas == []
    assert nota.status == Invoice.STATUS_ERROR
    assert "Código IBGE do município" in nota.error_message
