"""Smoke test do texto ESC/POS do DANFE (usado pelo agente local em
impressoras de rede/serial, que nao renderizam o HTML)."""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.invoices.fiscal import format_access_key
from apps.invoices.models import FiscalConfig
from apps.invoices.services import _danfe_nfce_text, emit_fiscal_invoice, print_fiscal_invoice
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db


def test_danfe_text_contains_key_fields(account, restaurant, branch, manager_user):
    product = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("25.00"),
    )
    config = FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        provider="manual", cnpj="11222333000181", uf="SP",
        environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
    )
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    add_order_item(order=order, product=product, quantity=1, user=manager_user)

    invoice = emit_fiscal_invoice(order, user=manager_user)

    with tenant_context(account):
        text = _danfe_nfce_text(invoice, config)

    assert "X-Burger" in text
    product_line = next(line for line in text.splitlines() if "X-Burger" in line)
    assert len(product_line) == 48
    assert product_line.endswith("R$ 25.00")
    assert invoice.number in text
    assert "HOMOLOGACAO" in text
    assert "AGUARDANDO AUTORIZACAO" in text
    # A chave de acesso formatada (blocos de 4 + espaco) passa de 48 colunas de
    # proposito — igual ao HTML (`word-break: break-all`), o impressora que
    # quebra a linha visualmente; nao e uma linha "normal" do cupom.
    other_lines = [line for line in text.split("\n") if line.strip() != format_access_key(invoice.access_key)]
    assert all(len(line) <= 48 for line in other_lines)


def test_print_fiscal_invoice_payload_has_text_and_qr(account, restaurant, branch, manager_user):
    product = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("25.00"),
    )
    FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        provider="manual", cnpj="11222333000181", uf="SP",
        environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
        qr_base_url="https://www.sefaz.sp.gov.br/nfce/qrcode", csc_id="000001", csc_token="ABC123",
    )
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    invoice = emit_fiscal_invoice(order, user=manager_user)

    job = print_fiscal_invoice(invoice, user=manager_user)

    assert job.payload["payload_version"] == 2
    assert job.payload["qr_data"] == invoice.qr_code_data
    assert "text_content" in job.payload
    assert "X-Burger" in job.payload["text_content"]
