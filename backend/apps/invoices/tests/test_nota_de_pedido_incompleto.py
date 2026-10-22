# O fixture `ambiente` vem importado do teste do provedor; o pytest o injeta
# pelo nome do parâmetro, e o ruff lê isso como redefinição.
# ruff: noqa: F811
"""Erros da loja (2026-10-19): 899, "a nota nao possui itens fiscais" e 866.

A venda que veio da nuvem chega em pedaços. A varredura dos pagos sem nota
montava a nota com o pedido pela metade: sem itens, ou sem pagamento — e aí o
documento ia com tPag=90, que a NFC-e não aceita (899). O reenvio em massa
repetia o mesmo envio fadado à recusa.
"""
import configparser
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.invoices.emissao_da_loja import emitir_pagos_sem_nota
from apps.invoices.models import Invoice
from apps.invoices.services import emit_fiscal_invoice, resend_fiscal_invoice
from apps.invoices.tests.quitacao import desfazer_quitacao
from apps.invoices.tests.test_acbrlib_provider import Comunicador, ambiente  # noqa: F401
from apps.invoices.tests.test_acbrlib_rejeicoes_comuns import _campo, _ini_emitido, _pagar
from apps.orders.models import Order

pytestmark = pytest.mark.django_db


def _emitir(ambiente, monkeypatch):
    comunicador = Comunicador("online")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    return emit_fiscal_invoice(ambiente.pedido, user=ambiente.user), comunicador


def _enviados(comunicador):
    return [c for c in comunicador.chamadas if c[0] == "/v1/nfe/emitir"]


def test_nfce_sem_pagamento_nao_vai_a_sefaz_com_tpag_90(ambiente, monkeypatch):
    desfazer_quitacao(ambiente.pedido)
    nota, comunicador = _emitir(ambiente, monkeypatch)

    assert _enviados(comunicador) == []
    assert nota.status == Invoice.STATUS_ERROR
    assert "não tem pagamento aprovado" in nota.error_message


def test_nfce_com_pagamento_menor_que_o_total_nao_vai_a_sefaz(ambiente, monkeypatch):
    _pagar(ambiente, "pix", "10.00")

    nota, comunicador = _emitir(ambiente, monkeypatch)

    assert _enviados(comunicador) == []
    assert "R$ 10.00, menos que o total de R$ 25.00" in nota.error_message


def test_pagamento_outros_leva_a_descricao(ambiente, monkeypatch):
    """tPag=99 sem xPag é a rejeição 441."""
    _pagar(ambiente, "other", "25.00")

    ini = _ini_emitido(ambiente, monkeypatch)

    assert _campo(ini, "tPag") == "99"
    assert _campo(ini, "xPag") == "other"


def test_pagamento_com_codigo_proprio_nao_leva_descricao(ambiente, monkeypatch):
    """xPag em tPag diferente de 99 é a rejeição 442."""
    _pagar(ambiente, "pix", "25.00")

    assert _campo(_ini_emitido(ambiente, monkeypatch), "xPag") is None


def test_troco_vai_tambem_na_secao_pag(ambiente, monkeypatch):
    """866 voltou na loja: o troco vai nos dois lugares que a ACBrLib pode ler."""
    _pagar(ambiente, "cash", "25.00", troco="5.00")

    leitor = configparser.ConfigParser(interpolation=None, strict=False)
    leitor.read_string(_ini_emitido(ambiente, monkeypatch))

    assert leitor["pag"]["vtroco"] == "5.00"
    assert leitor["pag001"]["vtroco"] == "5.00"


def test_varredura_espera_o_pedido_chegar_inteiro(ambiente, settings, monkeypatch):
    settings.SYNC_ENABLED, settings.SYNC_NODE_TYPE = True, "local"
    desfazer_quitacao(ambiente.pedido)  # o pagamento ainda não chegou
    Order.all_objects.filter(pk=ambiente.pedido.pk).update(status=Order.STATUS_PAID)
    comunicador = Comunicador("online")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)

    assert emitir_pagos_sem_nota() == 0
    assert not Invoice.all_objects.filter(order=ambiente.pedido).exists()

    _pagar(ambiente, "pix", "25.00")  # o pagamento chegou

    assert emitir_pagos_sem_nota() == 1
    assert Invoice.all_objects.get(order=ambiente.pedido).status == Invoice.STATUS_ISSUED


def test_reenvio_diz_o_que_falta_e_funciona_quando_chega(ambiente, monkeypatch):
    desfazer_quitacao(ambiente.pedido)
    nota, comunicador = _emitir(ambiente, monkeypatch)

    with pytest.raises(ValidationError, match="não tem pagamento aprovado"):
        resend_fiscal_invoice(nota, user=ambiente.user)
    assert _enviados(comunicador) == []

    _pagar(ambiente, "pix", "25.00")
    nota = resend_fiscal_invoice(nota, user=ambiente.user)

    assert nota.status == Invoice.STATUS_ISSUED
    assert _campo(_enviados(comunicador)[0][1]["ini"], "tPag") == "17"


def test_pedido_de_valor_zero_nao_gera_nfce(ambiente):
    from apps.invoices.services import fiscal_emission_skipped_reason

    Order.all_objects.filter(pk=ambiente.pedido.pk).update(total=Decimal("0.00"))
    ambiente.pedido.refresh_from_db()

    assert "valor zero" in fiscal_emission_skipped_reason(ambiente.pedido)
