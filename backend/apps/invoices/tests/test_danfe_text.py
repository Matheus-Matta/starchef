"""Smoke test do texto ESC/POS do DANFE (usado pelo agente local em
impressoras de rede/serial, que nao renderizam o HTML)."""
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.invoices.fiscal import format_access_key
from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.services import (
    _DANFE_WIDTH,
    _danfe_nfce_text,
    emit_fiscal_invoice,
    print_fiscal_invoice,
)
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import Payment, PaymentMethod

pytestmark = pytest.mark.django_db


def _authorize(invoice):
    invoice.status = Invoice.STATUS_ISSUED
    invoice.authorization_protocol = "135260000000001"
    invoice.authorized_at = timezone.now()
    invoice.save(update_fields=["status", "authorization_protocol", "authorized_at", "updated_at"])


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
    assert product_line.endswith("X-Burger")
    detail_line = next(line for line in text.splitlines() if "1,000 UN x 25,00" in line)
    assert detail_line.endswith("25,00")
    assert invoice.number in text
    assert "HOMOLOGACAO" in text
    assert "AGUARDANDO AUTORIZACAO" in text
    # A chave de acesso formatada (blocos de 4 + espaco) passa da largura de
    # proposito — igual ao HTML (`word-break: break-all`), e a impressora que
    # quebra a linha visualmente; nao e uma linha "normal" do cupom.
    assert format_access_key(invoice.access_key).split()[0] in text
    # Pela constante, e nao por um numero solto: uma termica generica de 80mm
    # nao TRUNCA o excedente, ela quebra para a linha de baixo — foi assim que
    # o ultimo digito do valor e o ultimo traco do separador sairam sozinhos
    # numa linha nova.
    assert all(len(line) <= _DANFE_WIDTH for line in text.splitlines())


def test_danfe_web_and_text_follow_receipt_layout_with_payment(
    account, restaurant, branch, manager_user
):
    product = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Pizza Grande", internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("42.50"),
    )
    FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        provider="manual", cnpj="11222333000181", uf="SP",
        trade_name="Loja Teste", ie="123456789", address_line="Rua Central, 100",
        environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
        qr_base_url="https://www.sefaz.sp.gov.br/nfce/qrcode", csc_id="000001", csc_token="ABC123",
    )
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    method = PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Cartao", method_type=PaymentMethod.TYPE_CARD,
    )
    Payment.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        order=order, payment_method=method, card_subtype=Payment.CARD_CREDIT,
        amount=Decimal("42.50"),
    )
    invoice = emit_fiscal_invoice(order, user=manager_user)
    _authorize(invoice)

    job = print_fiscal_invoice(invoice, user=manager_user)
    text = job.payload["text_content"]
    html = job.html_content

    ordered_text = [
        "DOCUMENTO AUXILIAR", "COD DESCRICAO", "QTD. TOTAL DE ITENS",
        "FORMA DE PAGAMENTO", "Via Consumidor", "CONSUMIDOR NAO IDENTIFICADO",
    ]
    positions = [text.index(value) for value in ordered_text]
    assert positions == sorted(positions)
    assert "CARTAO - CRÉDITO" in text
    assert text.splitlines()[0].strip() == "Loja Teste"
    assert "FORMA DE PAGAMENTO" in html
    assert "CARTAO - CRÉDITO" in html
    assert "42,50" in html
    assert "Via Consumidor" in html
    assert "QR Code da NFC-e" in html


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
    _authorize(invoice)

    job = print_fiscal_invoice(invoice, user=manager_user)

    assert job.payload["payload_version"] == 2
    assert job.payload["qr_data"] == invoice.qr_code_data
    assert "text_content" in job.payload
    assert "X-Burger" in job.payload["text_content"]
