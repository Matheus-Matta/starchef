"""Cancelar o pedido cancela a NFC-e na SEFAZ pela ACBrLib — e sem perder nada.

O caminho: `cancel_order` → `cancel_invoice_for_order` → o evento de
cancelamento (`NFE_Cancelar`). O defeito: a resposta do cancelamento traz o
protocolo do EVENTO, e ele era gravado por cima do protocolo de AUTORIZAÇÃO —
a nota perdia o número que prova que ela foi autorizada.
"""
import pytest
from django.core.exceptions import ValidationError

from apps.invoices.models import Invoice
from apps.invoices.services import emit_fiscal_invoice
from apps.invoices.tests.test_acbrlib_provider import XML, _resposta, ambiente  # noqa: F401
from apps.orders.models import Order
from apps.orders.services import cancel_order

pytestmark = pytest.mark.django_db

PROTOCOLO_AUTORIZACAO = "135000001"
PROTOCOLO_CANCELAMENTO = "135999999"


class Comunicador:
    """Autoriza a emissão; o cancelamento sai como a SEFAZ mandar."""

    def __init__(self, cancelamento="aceito"):
        self.cancelamento = cancelamento
        self.chamadas = []

    def __call__(self, metodo, url, json=None, headers=None, timeout=None):
        rota = url.split("acbr.local")[1]
        self.chamadas.append((rota, json))
        if rota == "/v1/nfe/cancelar":
            if self.cancelamento == "fora_do_prazo":
                return _resposta(200, {"situacao": "rejeitada", "cstat": 501,
                                       "motivo": "Prazo de cancelamento superior ao previsto"})
            return _resposta(200, {"situacao": "cancelada", "cstat": "135",
                                   "motivo": "Evento registrado e vinculado a NF-e",
                                   "chave": json["chave"], "protocolo": PROTOCOLO_CANCELAMENTO,
                                   "recebido_em": "2026-10-12T10:05:00-03:00"})
        return _resposta(200, {"situacao": "autorizada", "cstat": 100, "motivo": "Autorizado",
                               "chave": "35" + "1" * 42, "protocolo": PROTOCOLO_AUTORIZACAO,
                               "recebido_em": "2026-10-12T10:00:00-03:00", "xml": XML})


def _emitida(ambiente, monkeypatch, comunicador):  # noqa: F811
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    nota = emit_fiscal_invoice(ambiente.pedido, user=ambiente.user)
    assert nota.status == Invoice.STATUS_ISSUED
    return nota


def test_cancelar_o_pedido_cancela_a_nota_na_sefaz(ambiente, monkeypatch):  # noqa: F811
    comunicador = Comunicador()
    nota = _emitida(ambiente, monkeypatch, comunicador)

    cancel_order(ambiente.pedido, ambiente.user, "Cliente desistiu da compra")

    nota.refresh_from_db()
    rota, corpo = comunicador.chamadas[-1]
    assert rota == "/v1/nfe/cancelar"
    assert corpo["chave"] == nota.access_key
    assert len(corpo["justificativa"]) >= 15  # a SEFAZ exige de 15 a 255
    assert nota.status == Invoice.STATUS_CANCELLED
    # O protocolo da AUTORIZAÇÃO continua; o do cancelamento fica à parte.
    assert nota.authorization_protocol == PROTOCOLO_AUTORIZACAO
    assert nota.fiscal_payload["cancelamento"]["protocolo"] == PROTOCOLO_CANCELAMENTO


def test_sefaz_recusando_o_cancelamento_o_pedido_nao_e_cancelado(ambiente, monkeypatch):  # noqa: F811
    """Fora do prazo (NFC-e: 30 min na maioria das UFs) a SEFAZ recusa: cancelar
    só o pedido deixaria uma nota autorizada para uma venda que não existe."""
    nota = _emitida(ambiente, monkeypatch, Comunicador(cancelamento="fora_do_prazo"))

    with pytest.raises(ValidationError, match="Prazo de cancelamento"):
        cancel_order(ambiente.pedido, ambiente.user, "Cliente desistiu da compra")

    nota.refresh_from_db()
    ambiente.pedido.refresh_from_db()
    assert nota.status == Invoice.STATUS_ISSUED
    assert nota.authorization_protocol == PROTOCOLO_AUTORIZACAO
    assert ambiente.pedido.status != Order.STATUS_CANCELLED


def test_justificativa_curta_e_completada_ate_o_minimo(ambiente, monkeypatch):  # noqa: F811
    comunicador = Comunicador()
    _emitida(ambiente, monkeypatch, comunicador)

    cancel_order(ambiente.pedido, ambiente.user, "Erro")

    assert len(comunicador.chamadas[-1][1]["justificativa"]) >= 15

