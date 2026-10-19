# O fixture `ambiente` vem importado do teste do provedor; o pytest o injeta
# pelo nome do parâmetro, e o ruff lê isso como redefinição.
# ruff: noqa: F811
"""As duas recusas da SEFAZ que apareceram na loja (2026-10-15).

**866 — Ausência de troco.** A soma dos pagamentos passava do total da nota e
o troco só era lido do `change_amount` do dinheiro. Pagamento a mais no
cartão/PIX, ou desconto dado depois de pagar, deixava o troco em zero.

**613 — Chave difere da existente em BD (cNF diferente).** A SEFAZ já tem uma
nota AUTORIZADA com a nossa série e número, feita por outro emissor (outro
servidor com o mesmo CNPJ e série, contador voltado para trás). Reenviar a
mesma nota repete a recusa para sempre; o número está queimado.
"""
import re
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.invoices.fiscal import build_access_key
from apps.invoices.models import Invoice
from apps.invoices.services import emit_fiscal_invoice
from apps.invoices.tests.test_acbrlib_provider import (  # noqa: F401 — fixture
    XML,
    Comunicador,
    _resposta,
    ambiente,
)
from apps.payments.models import Payment, PaymentMethod

pytestmark = pytest.mark.django_db

CNF_DE_OUTRO_EMISSOR = "80715683"


def _campo(ini, nome):
    achado = re.search(rf"^{nome}=(.*)$", ini, re.M)
    return achado.group(1) if achado else None


def _pagar(ambiente, tipo, valor, troco="0.00"):
    pedido = ambiente.pedido
    metodo = PaymentMethod.objects.create(
        account=pedido.account, restaurant=pedido.restaurant, branch=pedido.branch,
        name=tipo, method_type=tipo,
    )
    Payment.objects.create(
        account=pedido.account, restaurant=pedido.restaurant, branch=pedido.branch,
        order=pedido, payment_method=metodo, amount=Decimal(valor), change_amount=Decimal(troco),
    )


def _ini_emitido(ambiente, monkeypatch):
    comunicador = Comunicador("online")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    emit_fiscal_invoice(ambiente.pedido, user=ambiente.user)
    return comunicador.chamadas[0][1]["ini"]


# ── 866: troco ────────────────────────────────────────────────────────────────

def test_pagamento_a_mais_no_cartao_vira_troco(ambiente, monkeypatch):
    """Nota de 25, cartão de 30, nenhum troco gravado: vTroco = 5,00."""
    _pagar(ambiente, "credit_card", "30.00")

    ini = _ini_emitido(ambiente, monkeypatch)

    assert _campo(ini, "vPag") == "30.00"
    assert _campo(ini, "vTroco") == "5.00"


def test_troco_do_dinheiro_continua_igual(ambiente, monkeypatch):
    """Dinheiro: 20 líquidos + 5 de troco = 25 entregues, troco 5 (como antes)."""
    _pagar(ambiente, "cash", "20.00", troco="5.00")
    _pagar(ambiente, "pix", "5.00")

    ini = _ini_emitido(ambiente, monkeypatch)

    assert _campo(ini, "vTroco") == "5.00"


def test_pagamento_exato_nao_leva_troco(ambiente, monkeypatch):
    _pagar(ambiente, "pix", "25.00")

    assert _campo(_ini_emitido(ambiente, monkeypatch), "vTroco") is None


# ── 613: o número já existe na SEFAZ ──────────────────────────────────────────

class SefazComNumeroUsado(Comunicador):
    """Recusa o 1º envio com 613; `cnf` decide de quem é a nota que já existe."""

    def __init__(self, cnf=None, recusar_sempre=False):
        super().__init__("online")
        self.cnf = cnf
        self.recusar_sempre = recusar_sempre
        self.chave_existente = None

    def __call__(self, metodo, url, json=None, headers=None, timeout=None):
        rota = url.split("acbr.local")[1]
        if rota == "/v1/nfe/consultar":
            self.chamadas.append((rota, json))
            return _resposta(200, {"situacao": "autorizada", "cstat": 100, "motivo": "Autorizado",
                                   "chave": json["chave"], "protocolo": "135777",
                                   "recebido_em": "2026-10-15T10:00:00-03:00", "xml": XML})
        emissoes = [c for c in self.chamadas if c[0] == "/v1/nfe/emitir"]
        if rota == "/v1/nfe/emitir" and (not emissoes or self.recusar_sempre):
            self.chamadas.append((rota, json))
            ini = json["ini"]
            self.chave_existente, _ = build_access_key(
                uf="SP", emission_date=timezone.now(), cnpj="11222333000181", model="65",
                series=_campo(ini, "serie"), number=_campo(ini, "nNF"),
                numeric_code=self.cnf or _campo(ini, "cNF"), emission_type="1",
            )
            return _resposta(200, {
                "situacao": "rejeitada", "cstat": 613,
                "motivo": "Rejeicao: Chave de Acesso difere da existente em BD Rejeicao: Codigo "
                          "Numerico informado na Chave de Acesso difere do Codigo Numerico da "
                          f"NF-e [{self.chave_existente}]",
            })
        return super().__call__(metodo, url, json=json, headers=headers, timeout=timeout)


def _emitir_com(ambiente, monkeypatch, sefaz):
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", sefaz)
    return emit_fiscal_invoice(ambiente.pedido, user=ambiente.user)


def test_numero_usado_por_outro_emissor_reemite_no_proximo_numero(ambiente, monkeypatch):
    """O cliente sai com nota: a nossa passa para o número seguinte, cNF novo."""
    sefaz = SefazComNumeroUsado(cnf=CNF_DE_OUTRO_EMISSOR)

    nota = _emitir_com(ambiente, monkeypatch, sefaz)

    assert nota.status == Invoice.STATUS_ISSUED
    assert nota.number == "2"
    emissoes = [c[1]["ini"] for c in sefaz.chamadas if c[0] == "/v1/nfe/emitir"]
    assert [_campo(ini, "nNF") for ini in emissoes] == ["1", "2"]
    assert _campo(emissoes[1], "cNF") != CNF_DE_OUTRO_EMISSOR
    # Fica registrado POR QUE a nota pulou um número (a SEFAZ tem o 1).
    assert nota.fiscal_payload["numero_ja_usado_na_sefaz"]["numero"] == "1"
    assert nota.fiscal_payload["numero_ja_usado_na_sefaz"]["chave"] == sefaz.chave_existente
    ambiente.config.refresh_from_db()
    assert ambiente.config.next_number == 3


def test_numero_que_e_desta_mesma_nota_e_adotado_sem_reemitir(ambiente, monkeypatch):
    """Mesmo cNF: é uma tentativa anterior DESTA nota que a SEFAZ autorizou.

    Reemitir em outro número daria duas notas para a mesma venda.
    """
    sefaz = SefazComNumeroUsado(cnf=None)

    nota = _emitir_com(ambiente, monkeypatch, sefaz)

    assert nota.status == Invoice.STATUS_ISSUED
    assert nota.number == "1"
    assert nota.access_key == sefaz.chave_existente
    assert nota.authorization_protocol == "135777"
    assert [c[0] for c in sefaz.chamadas].count("/v1/nfe/emitir") == 1


def test_numero_usado_de_novo_no_reenvio_vira_erro_sem_laco(ambiente, monkeypatch):
    """A série inteira ocupada: anda até o teto e para — a recusa fica para o humano."""
    from apps.invoices.numero_ja_usado import TENTATIVAS_DE_NUMERO

    sefaz = SefazComNumeroUsado(cnf=CNF_DE_OUTRO_EMISSOR, recusar_sempre=True)

    nota = _emitir_com(ambiente, monkeypatch, sefaz)

    assert nota.status == Invoice.STATUS_ERROR
    assert "613" in nota.error_message
    assert [c[0] for c in sefaz.chamadas].count("/v1/nfe/emitir") == 1 + TENTATIVAS_DE_NUMERO


def test_rejeicao_comum_nao_mexe_no_numero(ambiente, monkeypatch):
    comunicador = Comunicador("recusa")

    nota = _emitir_com(ambiente, monkeypatch, comunicador)

    assert nota.status == Invoice.STATUS_ERROR
    assert nota.number == "1"
    ambiente.config.refresh_from_db()
    assert ambiente.config.next_number == 2
