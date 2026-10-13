"""Cartão e PIX da maquininha à parte: `tpIntegra=2` na nota.

Sem o grupo do cartão, a SEFAZ recusa a NFC-e paga no crédito ou no débito
com 391 ("Não informados os dados do cartão"). O caixa não tem CNPJ da
credenciadora, bandeira nem autorização: a maquininha é separada do sistema.
É exatamente o caso do `tpIntegra=2` (pagamento NÃO integrado), que dispensa
esses três campos.
"""
from types import SimpleNamespace

import pytest

from apps.invoices.acbrlib.ini import _pagamento
from apps.invoices.documento_regras import DocumentoRegras


def _pago(tipo, subtipo=""):
    return SimpleNamespace(payment_method=SimpleNamespace(method_type=tipo), card_subtype=subtipo)


@pytest.mark.parametrize("tipo, subtipo, codigo", [
    ("card", "credit", "03"), ("card", "debit", "04"), ("pix", "", "17"),
])
def test_cartao_e_pix_saem_como_nao_integrados(tipo, subtipo, codigo):
    forma = DocumentoRegras._forma_de_pagamento(_pago(tipo, subtipo), "10.00")
    assert forma == {"forma_pagamento": codigo, "valor_pagamento": "10.00", "tipo_integracao": "2"}


def test_dinheiro_nao_leva_grupo_de_cartao():
    forma = DocumentoRegras._forma_de_pagamento(_pago("cash"), "10.00")
    assert "tipo_integracao" not in forma


def test_o_ini_da_acbrlib_escreve_tpintegra():
    secao = _pagamento({"forma_pagamento": "03", "valor_pagamento": "10.00", "tipo_integracao": "2"})
    assert secao == {"tPag": "03", "vPag": "10.00", "tpIntegra": "2"}
