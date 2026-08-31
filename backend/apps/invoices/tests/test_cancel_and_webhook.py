"""Cancelamento e webhook — os dois caminhos que tinham ficado de fora.

Cancelar uma nota autorizada e cancelar uma que nunca saiu daqui sao operacoes
diferentes: a primeira e um evento fiscal transmitido a SEFAZ, a segunda e um
descarte local, porque nao existe documento para cancelar. Tratar as duas como
uma so escondia as duas.

O webhook e o caminho normal da autorizacao assincrona. Ele engolia qualquer
erro com um `pass` e salvava a nota mantendo o `awaiting` da tentativa
anterior — fazendo o reprocessamento tratar como "nunca transmitida" uma nota
que a Focus ja tinha.
"""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.invoices.models import FiscalConfig, FiscalProfile, Invoice
from apps.invoices.providers import (
    FiscalProvider,
    FiscalRejection,
    FiscalUnavailable,
    register_provider,
)
from apps.invoices.services import (
    apply_focus_webhook,
    cancel_fiscal_invoice,
    emit_fiscal_invoice,
    is_fiscally_printable,
)
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db


@register_provider
class _AuthorizingProvider(FiscalProvider):
    name = "test_cancel_authorizes"
    transmits = True
    cancelled = 0

    def emit(self, invoice, config):
        invoice.provider = self.name
        invoice.status = Invoice.STATUS_ISSUED
        invoice.authorization_protocol = "135260000000001"
        invoice.access_key = "35" + "1" * 42
        return invoice

    def cancel(self, invoice, reason):
        type(self).cancelled += 1
        invoice.status = Invoice.STATUS_CANCELLED
        # Um provedor real devolve dados novos no cancelamento; eles precisam
        # sobreviver a gravacao.
        invoice.authorization_protocol = "999CANCELAMENTO"
        invoice.xml_content = "https://provedor/xml/cancelamento"
        return invoice


@register_provider
class _RefusesCancelProvider(_AuthorizingProvider):
    name = "test_cancel_refused"

    def cancel(self, invoice, reason):
        raise FiscalRejection("Rejeicao 501: prazo de cancelamento expirado.")


@register_provider
class _UnavailableCancelProvider(_AuthorizingProvider):
    name = "test_cancel_unavailable"

    def cancel(self, invoice, reason):
        raise FiscalUnavailable("SEFAZ indisponivel (simulado).")


@register_provider
class _NeverTransmitsProvider(FiscalProvider):
    name = "test_cancel_never_transmits"

    def emit(self, invoice, config):
        invoice.status = Invoice.STATUS_PENDING
        return invoice


@pytest.fixture(autouse=True)
def _reset():
    _AuthorizingProvider.cancelled = 0


def _config(account, restaurant, branch, provider):
    profile = FiscalProfile.objects.create(
        account=account, name=f"Perfil {uuid.uuid4().hex[:6]}",
        ncm="19059090", cfop="5102", csosn="102",
    )
    return FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch, provider=provider,
        cnpj="11222333000181", uf="SP", corporate_name="Loja Teste LTDA",
        environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
        default_profile=profile,
    )


def _invoice(account, restaurant, branch, user, provider):
    config = _config(account, restaurant, branch, provider)
    product = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="X-Burger",
        internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("25.00"),
        fiscal_profile=config.default_profile,
    )
    order = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=user
    )
    add_order_item(order=order, product=product, quantity=1, user=user)
    return emit_fiscal_invoice(order, user=user)


# ------------------------------------------------------------ cancelamento

def test_cancelling_an_authorized_note_transmits_the_event(
    account, restaurant, branch, manager_user
):
    invoice = _invoice(account, restaurant, branch, manager_user, _AuthorizingProvider.name)
    assert invoice.status == Invoice.STATUS_ISSUED

    cancelled = cancel_fiscal_invoice(invoice, reason="Erro do operador", user=manager_user)

    assert cancelled.status == Invoice.STATUS_CANCELLED
    assert _AuthorizingProvider.cancelled == 1
    # `update_fields` listava quatro campos e descartava o resto do que o
    # provedor devolve no cancelamento.
    assert cancelled.authorization_protocol == "999CANCELAMENTO"
    assert cancelled.xml_content == "https://provedor/xml/cancelamento"


def test_cancelling_a_note_that_was_never_authorized_is_local(
    account, restaurant, branch, manager_user
):
    """Nao existe documento na SEFAZ: nao ha evento a transmitir."""
    invoice = _invoice(account, restaurant, branch, manager_user, _NeverTransmitsProvider.name)
    assert invoice.status == Invoice.STATUS_PENDING

    cancelled = cancel_fiscal_invoice(invoice, reason="Venda desfeita", user=manager_user)

    assert cancelled.status == Invoice.STATUS_CANCELLED
    assert cancelled.error_message == "Venda desfeita"
    # E o marcador de espera some: senao o reprocessamento continuaria voltando
    # nela como se ainda houvesse o que transmitir.
    assert "awaiting" not in cancelled.fiscal_payload


def test_a_refused_cancellation_is_an_error_not_a_crash(
    account, restaurant, branch, manager_user
):
    """Prazo expirado e recusa do evento, nao falha do servidor."""
    from django.core.exceptions import ValidationError

    invoice = _invoice(account, restaurant, branch, manager_user, _RefusesCancelProvider.name)

    with pytest.raises(ValidationError, match="prazo de cancelamento"):
        cancel_fiscal_invoice(invoice, reason="Tarde demais", user=manager_user)

    invoice.refresh_from_db()
    assert invoice.status == Invoice.STATUS_ISSUED


def test_an_unavailable_provider_does_not_cancel_locally(
    account, restaurant, branch, manager_user
):
    """Rede caida nao pode marcar como cancelada uma nota viva na SEFAZ."""
    from django.core.exceptions import ValidationError

    invoice = _invoice(account, restaurant, branch, manager_user, _UnavailableCancelProvider.name)

    with pytest.raises(ValidationError, match="Tente novamente"):
        cancel_fiscal_invoice(invoice, reason="Erro", user=manager_user)

    invoice.refresh_from_db()
    assert invoice.status == Invoice.STATUS_ISSUED


def test_cancelling_twice_is_idempotent(account, restaurant, branch, manager_user):
    invoice = _invoice(account, restaurant, branch, manager_user, _AuthorizingProvider.name)
    cancel_fiscal_invoice(invoice, reason="Erro", user=manager_user)

    again = cancel_fiscal_invoice(invoice, reason="Erro", user=manager_user)

    assert again.status == Invoice.STATUS_CANCELLED
    assert _AuthorizingProvider.cancelled == 1


def test_a_cancelled_note_is_not_printable(account, restaurant, branch, manager_user):
    invoice = _invoice(account, restaurant, branch, manager_user, _AuthorizingProvider.name)
    invoice.emission_type = Invoice.EMISSION_CONTINGENCY  # contingencia legada
    invoice.save(update_fields=["emission_type", "updated_at"])

    cancelled = cancel_fiscal_invoice(invoice, reason="Erro", user=manager_user)

    assert is_fiscally_printable(cancelled) is False


# ------------------------------------------------------------------ webhook

def test_webhook_authorization_clears_the_pending_marker(
    account, restaurant, branch, manager_user
):
    """O aviso da Focus nao pode deixar a nota parecendo nao transmitida.

    O `awaiting` da tentativa anterior sobrevivia ao webhook, e o
    reprocessamento voltaria a transmitir uma nota que a Focus ja tem.
    """
    invoice = _invoice(account, restaurant, branch, manager_user, _NeverTransmitsProvider.name)
    with tenant_context(account):
        invoice.fiscal_payload = {**invoice.fiscal_payload, "awaiting": "transmission"}
        invoice.save(update_fields=["fiscal_payload", "updated_at"])

    apply_focus_webhook(invoice, {
        "status": "autorizado",
        "chave_nfe": "NFe35" + "3" * 42,
        "protocolo": "135260000000007",
    })
    invoice.refresh_from_db()

    assert invoice.status == Invoice.STATUS_ISSUED
    assert "awaiting" not in invoice.fiscal_payload


def test_webhook_rejection_is_persisted_as_a_rejection(
    account, restaurant, branch, manager_user
):
    invoice = _invoice(account, restaurant, branch, manager_user, _NeverTransmitsProvider.name)

    apply_focus_webhook(invoice, {
        "status": "erro_autorizacao",
        "mensagem_sefaz": "Rejeicao 539: duplicidade de NF-e",
    })
    invoice.refresh_from_db()

    assert invoice.status == Invoice.STATUS_ERROR
    assert invoice.fiscal_payload["failure"] == "rejection"
    assert "awaiting" not in invoice.fiscal_payload
    assert "Rejeicao 539" in invoice.error_message


def test_webhook_processing_keeps_the_note_awaiting_authorization(
    account, restaurant, branch, manager_user
):
    invoice = _invoice(account, restaurant, branch, manager_user, _NeverTransmitsProvider.name)

    apply_focus_webhook(invoice, {"status": "processando_autorizacao"})
    invoice.refresh_from_db()

    assert invoice.status == Invoice.STATUS_PENDING
    # `authorization` e nao `transmission`: a Focus ja tem o documento, entao a
    # proxima acao e consultar, nunca retransmitir.
    assert invoice.fiscal_payload["awaiting"] == "authorization"


def test_webhook_with_an_unexpected_payload_does_not_explode(
    account, restaurant, branch, manager_user
):
    """A Focus reenvia o aviso se receber erro; um payload torto viraria laco."""
    invoice = _invoice(account, restaurant, branch, manager_user, _NeverTransmitsProvider.name)

    apply_focus_webhook(invoice, {"status": "autorizado", "chave_nfe": "chave-invalida"})
    invoice.refresh_from_db()

    assert invoice.status == Invoice.STATUS_ERROR
