"""A nota da ACBrLib passa na SEFAZ de HOMOLOGAÇÃO, e a de produção sai intacta.

Em homologação a SEFAZ exige textos fixos: o primeiro item da NFC-e precisa se
chamar "NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"
(rejeição 373), e o destinatário, "NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO -
SEM VALOR FISCAL" (rejeição 598). A Focus aplica isso do lado dela; aqui o XML
nasce no backend, e sem a regra TODA nota de teste voltava rejeitada — não
dava para homologar o restaurante antes de ir para produção.
"""
import pytest

from apps.invoices.acbrlib.ini import TEXTO_HOMOLOGACAO_DESTINATARIO, TEXTO_HOMOLOGACAO_ITEM
from apps.invoices.models import FiscalConfig
from apps.invoices.tests.test_acbrlib_provider import _emitir, ambiente  # noqa: F401

pytestmark = pytest.mark.django_db


def _secao(ini, nome):
    corpo = ini.split(f"[{nome}]")[1].split("\n\n")[0]
    return dict(linha.split("=", 1) for linha in corpo.strip().splitlines())


def _emitir_com_cpf(ambiente, monkeypatch):  # noqa: F811
    from apps.invoices.services import emit_fiscal_invoice
    from apps.invoices.tests.test_acbrlib_provider import Comunicador

    comunicador = Comunicador("online")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    emit_fiscal_invoice(ambiente.pedido, user=ambiente.user, cpf="52998224725", cpf_name="Maria")
    return comunicador.chamadas[0][1]


def test_homologacao_usa_os_textos_que_a_sefaz_exige(ambiente, monkeypatch):  # noqa: F811
    corpo = _emitir_com_cpf(ambiente, monkeypatch)

    assert corpo["ambiente"] == FiscalConfig.ENV_HOMOLOGATION
    assert _secao(corpo["ini"], "Identificacao")["tpAmb"] == "2"
    assert _secao(corpo["ini"], "Produto001")["xProd"] == TEXTO_HOMOLOGACAO_ITEM
    assert _secao(corpo["ini"], "Destinatario")["xNome"] == TEXTO_HOMOLOGACAO_DESTINATARIO


def test_producao_sai_com_os_dados_reais(ambiente, monkeypatch):  # noqa: F811
    ambiente.config.environment = FiscalConfig.ENV_PRODUCTION
    ambiente.config.save()

    corpo = _emitir_com_cpf(ambiente, monkeypatch)

    assert corpo["ambiente"] == FiscalConfig.ENV_PRODUCTION
    assert _secao(corpo["ini"], "Identificacao")["tpAmb"] == "1"
    assert _secao(corpo["ini"], "Produto001")["xProd"] == "X-Burger"
    assert _secao(corpo["ini"], "Destinatario")["xNome"] == "Maria"
