"""Uma falha do provider real (SEFAZ/integrador fora do ar) nao pode travar o
fechamento da venda: a nota cai em contingencia (tpEmis=9), fica pending mas
imprimivel, e pode ser retransmitida depois via `reprocess_pending_fiscal_invoices`.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FiscalProvider, register_provider
from apps.invoices.services import emit_fiscal_invoice, reprocess_pending_fiscal_invoices, resend_fiscal_invoice
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db


@register_provider
class _AlwaysFailsProvider(FiscalProvider):
    name = "test_always_fails"

    def emit(self, invoice, config):
        raise RuntimeError("SEFAZ indisponivel (simulado)")


@register_provider
class _SucceedsOnRetryProvider(FiscalProvider):
    """Falha na primeira tentativa (emissao original), autoriza no reprocessamento."""

    name = "test_succeeds_on_retry"
    attempts = 0

    def emit(self, invoice, config):
        type(self).attempts += 1
        if type(self).attempts == 1:
            raise RuntimeError("SEFAZ indisponivel (simulado)")
        invoice.status = Invoice.STATUS_ISSUED
        invoice.authorization_protocol = "135250000000001"
        return invoice


def _make_product(account, restaurant, branch):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("25.00"),
    )


def _make_fiscal_config(account, restaurant, branch, provider):
    return FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        provider=provider, cnpj="11222333000181", uf="SP",
        environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
    )


def _make_order_with_item(restaurant, branch, product, user):
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=user)
    add_order_item(order=order, product=product, quantity=1, user=user)
    return order


def test_provider_failure_falls_back_to_contingency(account, restaurant, branch, manager_user):
    product = _make_product(account, restaurant, branch)
    _make_fiscal_config(account, restaurant, branch, provider="test_always_fails")
    order = _make_order_with_item(restaurant, branch, product, manager_user)

    invoice = emit_fiscal_invoice(order, user=manager_user)

    assert invoice.emission_type == Invoice.EMISSION_CONTINGENCY
    assert invoice.status == Invoice.STATUS_PENDING
    assert "SEFAZ indisponivel" in invoice.error_message
    assert invoice.access_key  # chave ainda foi gerada — nota e imprimivel


def test_reprocess_marks_issued_when_provider_recovers(account, restaurant, branch, manager_user):
    _SucceedsOnRetryProvider.attempts = 0
    product = _make_product(account, restaurant, branch)
    _make_fiscal_config(account, restaurant, branch, provider="test_succeeds_on_retry")
    order = _make_order_with_item(restaurant, branch, product, manager_user)

    invoice = emit_fiscal_invoice(order, user=manager_user)
    assert invoice.emission_type == Invoice.EMISSION_CONTINGENCY

    retried, issued = reprocess_pending_fiscal_invoices()
    invoice.refresh_from_db()

    assert retried == 1
    assert issued == 1
    assert invoice.status == Invoice.STATUS_ISSUED
    assert invoice.authorization_protocol == "135250000000001"


def test_resend_retries_only_the_chosen_contingency_note(account, restaurant, branch, manager_user):
    _SucceedsOnRetryProvider.attempts = 0
    product = _make_product(account, restaurant, branch)
    _make_fiscal_config(account, restaurant, branch, provider="test_succeeds_on_retry")
    order = _make_order_with_item(restaurant, branch, product, manager_user)
    invoice = emit_fiscal_invoice(order, user=manager_user)

    resent = resend_fiscal_invoice(invoice, user=manager_user)

    assert resent.pk == invoice.pk
    assert resent.status == Invoice.STATUS_ISSUED
    assert resent.authorization_protocol == "135250000000001"


def test_resend_refreshes_emission_date_and_access_key(account, restaurant, branch, manager_user):
    _SucceedsOnRetryProvider.attempts = 0
    product = _make_product(account, restaurant, branch)
    _make_fiscal_config(account, restaurant, branch, provider="test_succeeds_on_retry")
    order = _make_order_with_item(restaurant, branch, product, manager_user)
    invoice = emit_fiscal_invoice(order, user=manager_user)
    invoice.fiscal_payload["emission"] = "2025-01-10T12:00:00+00:00"
    invoice.access_key = "old-access-key"
    invoice.save(update_fields=["fiscal_payload", "access_key", "updated_at"])
    retry_time = datetime(2026, 8, 30, 18, 45, tzinfo=timezone.utc)

    with patch("apps.invoices.services.timezone.now", return_value=retry_time):
        resent = resend_fiscal_invoice(invoice, user=manager_user)

    assert resent.fiscal_payload["emission"] == retry_time.isoformat()
    assert resent.issued_at == retry_time
    assert resent.access_key != "old-access-key"
    assert resent.access_key[2:6] == "2608"


def test_resend_persists_new_failure_as_error(account, restaurant, branch, manager_user):
    product = _make_product(account, restaurant, branch)
    _make_fiscal_config(account, restaurant, branch, provider="test_always_fails")
    order = _make_order_with_item(restaurant, branch, product, manager_user)
    invoice = emit_fiscal_invoice(order, user=manager_user)

    resent = resend_fiscal_invoice(invoice, user=manager_user)

    assert resent.status == Invoice.STATUS_ERROR
    assert "SEFAZ indisponivel" in resent.error_message


def test_reprocess_ignores_notes_without_contingency(account, restaurant, branch, manager_user):
    """Uma nota `pending` sem contingencia (provider manual, scaffold) nao entra
    no reprocessamento — so notas que genuinamente falharam num provider real."""
    product = _make_product(account, restaurant, branch)
    _make_fiscal_config(account, restaurant, branch, provider="manual")
    order = _make_order_with_item(restaurant, branch, product, manager_user)

    invoice = emit_fiscal_invoice(order, user=manager_user)
    assert invoice.emission_type == Invoice.EMISSION_NORMAL
    assert invoice.status == Invoice.STATUS_PENDING

    retried, issued = reprocess_pending_fiscal_invoices()

    assert retried == 0
    assert issued == 0
