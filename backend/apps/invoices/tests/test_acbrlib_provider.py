"""O emissor ACBrLib: cada caminho do plano de contingência (FISCAL_ACBRLIB.md).

O comunicador é simulado no `requests.request`: o que se prova aqui é a
decisão do backend diante de cada resposta — autorizar, recusar, entrar em
contingência, esperar, consultar e retransmitir O MESMO XML.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import requests

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.services import (
    emit_fiscal_invoice,
    is_fiscally_printable,
    reprocess_pending_fiscal_invoices,
)
from apps.invoices.tests.certificado_de_teste import SENHA, pfx
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db

PFX = pfx(cnpj="11222333000181")

XML = "<nfeProc>assinado</nfeProc>"

#: Um emitente completo: a ACBrLib monta o XML inteiro aqui, e sem estes a
#: emissão para antes da SEFAZ (`test_acbrlib_dados_do_restaurante`).
EMITENTE = {
    "ie": "111222333444", "corporate_name": "Restaurante Teste LTDA", "trade_name": "Teste",
    "address_line": "Rua A", "address_number": "10", "district": "Centro", "city": "São Paulo",
    "city_ibge": "3550308", "zip_code": "01001000",
}


class Comunicador:
    """O comunicador falso: responde por rota, e registra cada chamada."""

    def __init__(self, sefaz="online"):
        self.sefaz = sefaz
        self.chamadas = []

    def __call__(self, metodo, url, json=None, headers=None, timeout=None):
        rota = url.split("acbr.local")[1]
        self.chamadas.append((rota, json))
        if self.sefaz == "comunicador_fora":
            raise requests.ConnectionError("recusada")
        if self.sefaz == "timeout":
            raise requests.Timeout("lento")
        if self.sefaz == "timeout_so_na_normal" and json.get("tp_emis") == "1":
            raise requests.Timeout("lento")
        if rota == "/v1/nfe/emitir" and json["tp_emis"] == "9":
            return _resposta(200, {"situacao": "contingencia", "chave": "3" * 44, "xml": XML,
                                   "qrcode": "https://qr?p=offline"})
        if self.sefaz == "fora":
            return _resposta(503, {"erro": "sem_comunicacao", "mensagem": "SEFAZ fora"})
        if self.sefaz == "recusa":
            return _resposta(200, {"situacao": "rejeitada", "cstat": 778, "motivo": "NCM inexistente"})
        return _resposta(200, {"situacao": "autorizada", "cstat": 100, "motivo": "Autorizado",
                               "chave": "35" + "1" * 42, "protocolo": "135000001",
                               "recebido_em": "2026-10-09T10:00:00-03:00", "xml": XML})


def _resposta(status, corpo):
    return SimpleNamespace(status_code=status, json=lambda: corpo)


@pytest.fixture
def ambiente(settings, monkeypatch, account, restaurant, branch, manager_user):
    settings.ACBRLIB_URL = "http://acbr.local"
    settings.ACBRLIB_TOKEN = "segredo"
    monkeypatch.setattr("apps.invoices.acbrlib.provider.segredos_de", lambda _c: SimpleNamespace(
        certificate_base64=PFX, certificate_password=SENHA, csc_id="000001", csc_token="CSC"))
    config = FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        provider=FiscalConfig.PROVIDER_ACBRLIB, cnpj="11222333000181", uf="SP",
        environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
        csc_id="000001", csc_token="CSC", **EMITENTE,
    )
    produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}",
                                     sale_price=Decimal("25.00"))
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                          user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
    return SimpleNamespace(config=config, pedido=pedido, user=manager_user)


def _emitir(ambiente, monkeypatch, sefaz):
    comunicador = Comunicador(sefaz)
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    return emit_fiscal_invoice(ambiente.pedido, user=ambiente.user), comunicador


def test_autorizada_vira_emitida_com_protocolo_e_xml(ambiente, monkeypatch):
    nota, comunicador = _emitir(ambiente, monkeypatch, "online")

    assert nota.status == Invoice.STATUS_ISSUED
    assert nota.authorization_protocol == "135000001"
    assert nota.xml_content == XML
    rota, corpo = comunicador.chamadas[0]
    assert rota == "/v1/nfe/emitir" and corpo["tp_emis"] == "1"
    assert "[Identificacao]" in corpo["ini"] and "tpEmis=1" in corpo["ini"]
    assert "[Produto001]" in corpo["ini"] and "[pag001]" in corpo["ini"]
    assert corpo["certificado"]["pfx_base64"] == PFX


def test_recusa_da_sefaz_sem_contingencia_ligada_vira_erro(ambiente, monkeypatch):
    # Com a contingência ligada a recusa sai em contingência para imprimir
    # (test_acbrlib_contingencia_para_imprimir).
    nota, comunicador = _emitir(ambiente, monkeypatch, "recusa")

    assert nota.status == Invoice.STATUS_ERROR
    assert "NCM inexistente" in nota.error_message
    assert nota.emission_type == Invoice.EMISSION_NORMAL
    assert len(comunicador.chamadas) == 1


def test_sefaz_fora_com_contingencia_assina_offline_e_imprime(ambiente, monkeypatch):
    ambiente.config.offline_contingency = True
    ambiente.config.save()
    nota, comunicador = _emitir(ambiente, monkeypatch, "fora")

    assert nota.emission_type == Invoice.EMISSION_CONTINGENCY
    assert nota.status == Invoice.STATUS_PENDING
    assert nota.xml_content == XML and nota.qr_code_data == "https://qr?p=offline"
    assert nota.fiscal_payload["awaiting"] == "transmission"
    assert is_fiscally_printable(nota)
    _, corpo = comunicador.chamadas[1]
    assert corpo["tp_emis"] == "9" and "dhCont=" in corpo["ini"] and "xJust=" in corpo["ini"]


def test_sefaz_fora_sem_contingencia_so_espera_transmitir(ambiente, monkeypatch):
    nota, comunicador = _emitir(ambiente, monkeypatch, "fora")

    assert nota.emission_type == Invoice.EMISSION_NORMAL
    assert nota.fiscal_payload["awaiting"] == "transmission"
    assert len(comunicador.chamadas) == 1


def test_tempo_esgotado_sem_contingencia_ligada_so_consulta(ambiente, monkeypatch):
    nota, comunicador = _emitir(ambiente, monkeypatch, "timeout")

    assert nota.fiscal_payload["awaiting"] == "reconciliation"
    assert nota.emission_type == Invoice.EMISSION_NORMAL
    assert len(comunicador.chamadas) == 1


def test_comunicador_fora_nao_assina_e_a_nota_volta_ao_normal(ambiente, monkeypatch):
    ambiente.config.offline_contingency = True
    ambiente.config.save()
    nota, _ = _emitir(ambiente, monkeypatch, "comunicador_fora")

    assert nota.emission_type == Invoice.EMISSION_NORMAL
    assert nota.fiscal_payload["awaiting"] == "transmission"


def test_retransmissao_envia_o_mesmo_xml_sem_refazer_a_chave(ambiente, monkeypatch):
    ambiente.config.offline_contingency = True
    ambiente.config.save()
    nota, _ = _emitir(ambiente, monkeypatch, "fora")
    chave_impressa = nota.access_key

    comunicador = Comunicador("online")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    reprocess_pending_fiscal_invoices()

    nota.refresh_from_db()
    rota, corpo = comunicador.chamadas[0]
    assert rota == "/v1/nfe/transmitir" and corpo["xml"] == XML
    assert chave_impressa == "3" * 44  # a do cupom, até a SEFAZ responder
    assert nota.status == Invoice.STATUS_ISSUED


def test_o_fuso_do_dhemi_vai_explicito_para_o_comunicador():
    """A data vai ao INI sem fuso e a ACBrLib acrescentava o do container (UTC):
    a NFC-e das 22:36 de Brasília saía +00:00, três horas "atrasada" (704)."""
    from apps.invoices.acbrlib.ini import fuso_acbr

    assert fuso_acbr() == "-03:00"
