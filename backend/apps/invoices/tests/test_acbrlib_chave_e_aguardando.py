# ruff: noqa: F811 — o fixture `ambiente` é injetado pelo nome do parâmetro.
"""Dois defeitos da ACBrLib vistos na loja (2026-11-19).

1. `Sessão "NFCe_.A_P" não encontrada no arquivo "ACBrNFeServicos"`: a chave
   nascia com cUF "00" quando a UF estava em branco no cadastro fiscal (e vinha
   do restaurante só no XML). A ACBrLib consulta pela UF da chave, e o
   `CUFtoUF` dela devolve ".A" para código desconhecido.
2. A nota "aguardando autorização" não imprimia: quem pede o cupom (o PDV em
   laço, ou o botão de imprimir) agora a recebe em contingência.
"""
import pytest

from apps.invoices.chave_do_emitente import consultavel, corrigir
from apps.invoices.fiscal import dv_mod11
from apps.invoices.models import Invoice
from apps.invoices.services import print_fiscal_invoice, refresh_fiscal_invoice_status
from apps.invoices.tests.test_acbrlib_contingencia_para_imprimir import (
    CHAVE_CONTINGENCIA,
    ComunicadorComConsulta,
    _com_contingencia,
    _emitir,
)
from apps.invoices.tests.test_acbrlib_provider import _resposta, ambiente  # noqa: F401

pytestmark = pytest.mark.django_db

CNPJ = "11222333000181"


class AindaProcessando(ComunicadorComConsulta):
    def __call__(self, metodo, url, json=None, headers=None, timeout=None):
        if url.endswith("/v1/nfe/consultar"):
            self.chamadas.append(("/v1/nfe/consultar", json))
            return _resposta(200, {"situacao": "processando", "cstat": 105, "motivo": "Em processamento"})
        return super().__call__(metodo, url, json=json, headers=headers, timeout=timeout)


def _aguardando(ambiente, monkeypatch):
    nota = _emitir(ambiente, monkeypatch, ComunicadorComConsulta("processando"))
    assert nota.status == Invoice.STATUS_PENDING
    assert nota.fiscal_payload["awaiting"] == "authorization"
    _com_contingencia(ambiente)
    return nota


def test_chave_usa_uf_e_cnpj_do_restaurante_quando_o_cadastro_fiscal_esta_em_branco(ambiente, monkeypatch):
    restaurante = ambiente.pedido.restaurant
    restaurante.state, restaurante.cnpj = "SP", CNPJ
    restaurante.save()
    ambiente.config.uf, ambiente.config.cnpj = "", ""
    ambiente.config.save()

    nota = _emitir(ambiente, monkeypatch, ComunicadorComConsulta("processando"))

    assert nota.access_key[:2] == "35"
    assert nota.access_key[6:20] == CNPJ


def test_chave_antiga_com_cuf_zerado_e_corrigida_antes_de_consultar(ambiente, monkeypatch):
    nota = _emitir(ambiente, monkeypatch, ComunicadorComConsulta("processando"))
    corpo = "00" + nota.access_key[2:6] + "0" * 14 + nota.access_key[20:43]
    nota.access_key = f"{corpo}{dv_mod11(corpo)}"
    nota.save()
    assert not consultavel(nota.access_key)

    comunicador = ComunicadorComConsulta("online", consulta="autorizada")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    nota = refresh_fiscal_invoice_status(nota)

    chave = comunicador.chamadas[0][1]["chave"]
    assert consultavel(chave) and chave[:2] == "35" and chave[6:20] == CNPJ
    assert corrigir(chave, ambiente.config) == chave  # boa, volta como está
    assert nota.status == Invoice.STATUS_ISSUED and nota.access_key == chave


def test_aguardando_autorizacao_imprime_em_contingencia_quando_o_terminal_espera(ambiente, monkeypatch):
    nota = _aguardando(ambiente, monkeypatch)
    chave_normal = nota.access_key
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", AindaProcessando("online"))

    nota = refresh_fiscal_invoice_status(nota, manual_print=True)

    assert nota.emission_type == Invoice.EMISSION_CONTINGENCY
    assert nota.access_key == CHAVE_CONTINGENCIA
    assert nota.fiscal_payload["chave_normal"] == chave_normal


def test_consulta_sem_terminal_esperando_continua_aguardando(ambiente, monkeypatch):
    nota = _aguardando(ambiente, monkeypatch)
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", AindaProcessando("online"))

    nota = refresh_fiscal_invoice_status(nota)

    assert nota.emission_type == Invoice.EMISSION_NORMAL
    assert nota.fiscal_payload["awaiting"] == "authorization"


def test_botao_de_imprimir_na_nota_aguardando_assina_em_contingencia(ambiente, monkeypatch):
    nota = _aguardando(ambiente, monkeypatch)
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", ComunicadorComConsulta("online"))

    job = print_fiscal_invoice(nota, user=ambiente.user, manual_only=True)

    nota.refresh_from_db()
    assert job is not None
    assert nota.emission_type == Invoice.EMISSION_CONTINGENCY
    assert nota.fiscal_payload["chave_normal"]
