"""Backend e comunicador de verdade, por HTTP, com a SEFAZ simulada.

Só roda com um comunicador no ar (`ACBRLIB_E2E_URL`, ex. `http://127.0.0.1:8099`,
subido com `ACBR_SIMULADOR=1`). Prova o que os testes com o comunicador falso
não provam: que o INI que o backend monta é lido pelo comunicador, que a chave
que o comunicador calcula é a MESMA que o backend calculou, e que a
contingência assinada volta e é transmitida depois.
"""
import os
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import requests

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.services import emit_fiscal_invoice, reprocess_pending_fiscal_invoices
from apps.invoices.tests.test_acbrlib_provider import EMITENTE
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

URL = os.environ.get("ACBRLIB_E2E_URL", "")
pytestmark = [pytest.mark.django_db, pytest.mark.skipif(not URL, reason="sem comunicador no ar")]


def _modo(modo):
    """O simulador lê o modo do ambiente dele; o teste o troca pela rota de apoio."""
    token = os.environ.get("ACBRLIB_E2E_TOKEN", "")
    requests.post(f"{URL}/_simulador/modo", json={"modo": modo}, timeout=5,
                  headers={"Authorization": f"Bearer {token}"})


@pytest.fixture
def venda(settings, monkeypatch, account, restaurant, branch, manager_user):
    settings.ACBRLIB_URL = URL
    settings.ACBRLIB_TOKEN = os.environ.get("ACBRLIB_E2E_TOKEN", "")
    monkeypatch.setattr("apps.invoices.acbrlib.provider.segredos_de", lambda _c: SimpleNamespace(
        certificate_base64="UEZY", certificate_password="1", csc_id="000001", csc_token="CSC"))
    FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch, uf="SP", cnpj="11222333000181",
        provider=FiscalConfig.PROVIDER_ACBRLIB, environment=FiscalConfig.ENV_HOMOLOGATION,
        series=1, next_number=7, offline_contingency=True, csc_id="000001", csc_token="CSC",
        **EMITENTE,
    )
    produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     name="Suco", internal_code=f"S{uuid.uuid4().hex[:6]}",
                                     sale_price=Decimal("12.50"))
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                          user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=2, user=manager_user)
    return SimpleNamespace(pedido=pedido, user=manager_user)


def test_autoriza_com_a_mesma_chave_que_o_backend_calculou(venda):
    _modo("online")
    nota = emit_fiscal_invoice(venda.pedido, user=venda.user)
    assert nota.status == Invoice.STATUS_ISSUED, nota.error_message
    assert nota.access_key[25:34] == "000000007" and nota.authorization_protocol


def test_sefaz_fora_contingencia_e_depois_transmite(venda):
    _modo("fora")
    nota = emit_fiscal_invoice(venda.pedido, user=venda.user)
    assert nota.emission_type == Invoice.EMISSION_CONTINGENCY, nota.error_message
    chave_do_cupom = nota.access_key
    assert chave_do_cupom[34] == "9"

    _modo("online")
    reprocess_pending_fiscal_invoices()
    nota.refresh_from_db()
    assert nota.status == Invoice.STATUS_ISSUED and nota.access_key == chave_do_cupom
