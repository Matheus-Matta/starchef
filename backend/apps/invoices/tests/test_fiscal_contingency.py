"""Uma falha do provider nao pode travar o fechamento da venda — mas o motivo
da falha decide o que acontece com a nota.

Indisponibilidade (rede, SEFAZ fora do ar) deixa a nota `pending` esperando
transmissao, e `reprocess_pending_fiscal_invoices` volta nela. Rejeicao
tributaria vira `error` e nao e retentada: reenviar repetiria a recusa. Nenhum
dos dois casos gera cupom fiscal, porque nenhum deles produziu documento
autorizado — a chave montada aqui nao existe na SEFAZ.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import (
    FiscalConfigurationError,
    FiscalProvider,
    FiscalRejection,
    FiscalUnavailable,
    register_provider,
)
from apps.invoices.services import (
    emit_fiscal_invoice,
    is_fiscally_printable,
    reprocess_pending_fiscal_invoices,
    resend_fiscal_invoice,
)
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db


@register_provider
class _UnavailableProvider(FiscalProvider):
    name = "test_unavailable"
    transmits = True

    def emit(self, invoice, config):
        raise FiscalUnavailable("SEFAZ indisponivel (simulado)")


@register_provider
class _RejectingProvider(FiscalProvider):
    name = "test_rejects"
    transmits = True

    def emit(self, invoice, config):
        raise FiscalRejection("Rejeicao 539: duplicidade de NF-e (simulado)")


@register_provider
class _MisconfiguredProvider(FiscalProvider):
    name = "test_misconfigured"
    transmits = True

    def emit(self, invoice, config):
        raise FiscalConfigurationError("Certificado vencido (simulado)")


@register_provider
class _ReconcilesOnStatusProvider(FiscalProvider):
    """Perdeu a resposta do POST; a consulta encontra a nota ja autorizada."""

    name = "test_reconciles"
    transmits = True

    def emit(self, invoice, config):
        raise AssertionError("Uma nota em reconciliacao nunca pode ser reenviada.")

    def status(self, invoice):
        invoice.status = Invoice.STATUS_ISSUED
        invoice.authorization_protocol = "135250000000007"
        return invoice.status


@register_provider
class _SucceedsOnRetryProvider(FiscalProvider):
    """Indisponivel na primeira tentativa, autoriza no reprocessamento."""

    name = "test_succeeds_on_retry"
    transmits = True
    attempts = 0

    def emit(self, invoice, config):
        type(self).attempts += 1
        if type(self).attempts == 1:
            raise FiscalUnavailable("SEFAZ indisponivel (simulado)")
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


def _emit(account, restaurant, branch, user, provider):
    product = _make_product(account, restaurant, branch)
    _make_fiscal_config(account, restaurant, branch, provider=provider)
    order = _make_order_with_item(restaurant, branch, product, user)
    return emit_fiscal_invoice(order, user=user)


def test_provider_unavailable_keeps_the_note_awaiting_transmission(
    account, restaurant, branch, manager_user
):
    invoice = _emit(account, restaurant, branch, manager_user, "test_unavailable")

    assert invoice.status == Invoice.STATUS_PENDING
    assert invoice.fiscal_payload["awaiting"] == "transmission"
    assert "SEFAZ indisponivel" in invoice.error_message
    # A chave existe (o documento foi montado), mas nao e um documento fiscal
    # valido enquanto nada tiver sido transmitido.
    assert invoice.access_key
    assert invoice.emission_type == Invoice.EMISSION_NORMAL
    assert is_fiscally_printable(invoice) is False


def test_tax_rejection_is_an_error_and_is_never_retried(account, restaurant, branch, manager_user):
    invoice = _emit(account, restaurant, branch, manager_user, "test_rejects")

    assert invoice.status == Invoice.STATUS_ERROR
    assert invoice.emission_type == Invoice.EMISSION_NORMAL
    assert "Rejeicao 539" in invoice.error_message
    assert is_fiscally_printable(invoice) is False

    retried, issued = reprocess_pending_fiscal_invoices()

    assert (retried, issued) == (0, 0)


def test_configuration_error_is_separated_from_rejection(account, restaurant, branch, manager_user):
    invoice = _emit(account, restaurant, branch, manager_user, "test_misconfigured")

    assert invoice.status == Invoice.STATUS_ERROR
    assert invoice.fiscal_payload["failure"] == "configuration"
    assert "Certificado vencido" in invoice.error_message


def test_reprocess_marks_issued_when_provider_recovers(account, restaurant, branch, manager_user):
    _SucceedsOnRetryProvider.attempts = 0
    invoice = _emit(account, restaurant, branch, manager_user, "test_succeeds_on_retry")
    assert invoice.fiscal_payload["awaiting"] == "transmission"

    retried, issued = reprocess_pending_fiscal_invoices()
    invoice.refresh_from_db()

    assert retried == 1
    assert issued == 1
    assert invoice.status == Invoice.STATUS_ISSUED
    assert invoice.authorization_protocol == "135250000000001"
    assert is_fiscally_printable(invoice) is True


def test_resend_retries_only_the_chosen_pending_note(account, restaurant, branch, manager_user):
    _SucceedsOnRetryProvider.attempts = 0
    invoice = _emit(account, restaurant, branch, manager_user, "test_succeeds_on_retry")

    resent = resend_fiscal_invoice(invoice, user=manager_user)

    assert resent.pk == invoice.pk
    assert resent.status == Invoice.STATUS_ISSUED
    assert resent.authorization_protocol == "135250000000001"


def test_resend_refreshes_emission_date_and_access_key(account, restaurant, branch, manager_user):
    _SucceedsOnRetryProvider.attempts = 0
    invoice = _emit(account, restaurant, branch, manager_user, "test_succeeds_on_retry")
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


def test_resend_persists_a_new_rejection_as_error(account, restaurant, branch, manager_user):
    invoice = _emit(account, restaurant, branch, manager_user, "test_rejects")

    resent = resend_fiscal_invoice(invoice, user=manager_user)

    assert resent.status == Invoice.STATUS_ERROR
    assert "Rejeicao 539" in resent.error_message


def test_resend_keeps_an_unavailable_note_awaiting_transmission(
    account, restaurant, branch, manager_user
):
    invoice = _emit(account, restaurant, branch, manager_user, "test_unavailable")

    resent = resend_fiscal_invoice(invoice, user=manager_user)

    assert resent.status == Invoice.STATUS_PENDING
    assert resent.fiscal_payload["awaiting"] == "transmission"


def test_reprocess_ignores_notes_from_a_provider_that_never_transmits(
    account, restaurant, branch, manager_user
):
    """Uma nota `pending` do provider manual (scaffold) nao espera autorizacao de
    ninguem: nao ha o que reconsultar nem o que retransmitir."""
    invoice = _emit(account, restaurant, branch, manager_user, "manual")
    assert invoice.emission_type == Invoice.EMISSION_NORMAL
    assert invoice.status == Invoice.STATUS_PENDING

    retried, issued = reprocess_pending_fiscal_invoices()

    assert (retried, issued) == (0, 0)


def test_legacy_contingency_notes_are_still_retransmitted(account, restaurant, branch, manager_user):
    """Notas gravadas com tpEmis=9 pelo comportamento anterior seguem no laco.

    Elas nao tem `awaiting` no payload; a unica leitura razoavel e que nunca
    chegaram ao provedor.
    """
    _SucceedsOnRetryProvider.attempts = 1  # a proxima tentativa autoriza
    invoice = _emit(account, restaurant, branch, manager_user, "test_succeeds_on_retry")
    invoice.status = Invoice.STATUS_PENDING
    invoice.emission_type = Invoice.EMISSION_CONTINGENCY
    invoice.fiscal_payload = {"cNF": invoice.fiscal_payload.get("cNF", "00000001")}
    invoice.save(update_fields=["status", "emission_type", "fiscal_payload", "updated_at"])

    retried, issued = reprocess_pending_fiscal_invoices()
    invoice.refresh_from_db()

    assert (retried, issued) == (1, 1)
    assert invoice.status == Invoice.STATUS_ISSUED


def test_resend_of_an_ambiguous_note_consults_instead_of_retransmitting(
    account, restaurant, branch, manager_user
):
    """Reenviar uma nota que pode ja existir no provedor criaria a segunda via.

    O provider deste teste levanta se `emit` for chamado: a unica acao aceitavel
    e consultar.
    """
    invoice = _emit(account, restaurant, branch, manager_user, "test_reconciles")
    invoice.fiscal_payload = {**invoice.fiscal_payload, "awaiting": "reconciliation"}
    invoice.status = Invoice.STATUS_PENDING
    invoice.save(update_fields=["fiscal_payload", "status", "updated_at"])

    resent = resend_fiscal_invoice(invoice, user=manager_user)

    assert resent.status == Invoice.STATUS_ISSUED
    assert resent.authorization_protocol == "135250000000007"
