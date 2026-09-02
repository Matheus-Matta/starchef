"""O cupom fiscal sai quando a autorizacao chega, nao antes e nao nunca.

Numa venda offline a NFC-e nao esta autorizada no momento do pagamento, entao o
DANFE nao pode sair ali: a chave montada localmente nao existe na SEFAZ. Antes,
nada criava o trabalho de impressao quando a autorizacao chegava depois — a nota
ficava autorizada no banco e o cliente nunca recebia o documento.

Aqui se garante que os quatro caminhos que autorizam uma nota tardiamente
enfileiram o DANFE, e que isso nunca produz cupom duplicado.
"""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.invoices.models import FiscalConfig, FiscalProfile, Invoice
from apps.invoices.providers import (
    FiscalNotFound,
    FiscalProvider,
    FiscalUnavailable,
    register_provider,
)
from apps.invoices.services import (
    emit_fiscal_invoice,
    ensure_fiscal_print_job,
    print_sale_documents,
    refresh_fiscal_invoice_status,
    reprocess_pending_fiscal_invoices,
    resend_fiscal_invoice,
)
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.printers.models import PrintJob, Printer

pytestmark = pytest.mark.django_db


@register_provider
class _AuthorizesOnRetryProvider(FiscalProvider):
    """Indisponivel na venda, autoriza quando a conexao volta."""

    name = "test_late_authorization"
    transmits = True
    attempts = 0

    def emit(self, invoice, config):
        type(self).attempts += 1
        if type(self).attempts == 1:
            raise FiscalUnavailable("SEFAZ indisponivel (simulado)")
        invoice.status = Invoice.STATUS_ISSUED
        invoice.authorization_protocol = "135260000000001"
        return invoice

    def status(self, invoice):
        invoice.status = Invoice.STATUS_ISSUED
        invoice.authorization_protocol = "135260000000009"
        return invoice.status


@pytest.fixture(autouse=True)
def _reset_provider():
    _AuthorizesOnRetryProvider.attempts = 0


@pytest.fixture
def printer(account, restaurant, branch, manager_user):
    return Printer.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Caixa",
        auto_print=True, created_by=manager_user, updated_by=manager_user,
    )


@pytest.fixture
def fiscal_config(account, restaurant, branch):
    profile = FiscalProfile.objects.create(
        account=account, name=f"Perfil {uuid.uuid4().hex[:6]}",
        ncm="19059090", cfop="5102", csosn="102",
    )
    return FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        provider=_AuthorizesOnRetryProvider.name, cnpj="11222333000181", uf="SP",
        corporate_name="Loja Teste LTDA", ie="123456789", address_line="Rua Central",
        address_number="100", district="Centro", city="Sao Paulo", city_ibge="3550308",
        zip_code="01001000", csc_id="000001", csc_token="ABC123",
        environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
        default_profile=profile,
    )


@pytest.fixture
def pending_invoice(account, restaurant, branch, manager_user, fiscal_config):
    """Venda paga cuja nota ficou aguardando transmissao."""
    product = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="X-Burger",
        internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("25.00"),
        fiscal_profile=fiscal_config.default_profile,
    )
    order = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user
    )
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    invoice = emit_fiscal_invoice(order, user=manager_user)
    assert invoice.status == Invoice.STATUS_PENDING
    return invoice


def _fiscal_jobs(order):
    return PrintJob.all_objects.filter(order=order, job_type=PrintJob.TYPE_FISCAL)


def test_payment_prints_only_the_receipt_while_the_note_is_pending(
    account, pending_invoice, printer, manager_user
):
    order = pending_invoice.order

    with tenant_context(account):
        print_sale_documents(order, invoice=pending_invoice, user=manager_user)

    types = sorted(job.job_type for job in PrintJob.all_objects.filter(order=order))
    assert types == [PrintJob.TYPE_RECEIPT]


def test_reprocess_enqueues_the_danfe_when_authorization_arrives(
    account, pending_invoice, printer, manager_user
):
    order = pending_invoice.order
    with tenant_context(account):
        print_sale_documents(order, invoice=pending_invoice, user=manager_user)
    assert not _fiscal_jobs(order).exists()

    retried, issued = reprocess_pending_fiscal_invoices()
    pending_invoice.refresh_from_db()

    assert (retried, issued) == (1, 1)
    assert pending_invoice.status == Invoice.STATUS_ISSUED
    job = _fiscal_jobs(order).get()
    # Sem impressora resolvida o agente local pula o trabalho e a nota nunca sai.
    assert job.printer_id == printer.id


def test_resend_enqueues_the_danfe(pending_invoice, printer, manager_user):
    order = pending_invoice.order

    resend_fiscal_invoice(pending_invoice, user=manager_user)

    assert _fiscal_jobs(order).count() == 1


def test_refresh_status_endpoint_enqueues_the_danfe(
    account, pending_invoice, printer, api_client
):
    """Consultar uma nota que a SEFAZ ja autorizou tambem solta o cupom.

    O cenario real e o de uma nota transmitida e ainda processando: `provider`
    fica preenchido pelo proprio `emit`, e e ele que a consulta usa.
    """
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    pending_invoice.provider = _AuthorizesOnRetryProvider.name
    pending_invoice.fiscal_payload = {**pending_invoice.fiscal_payload, "awaiting": "authorization"}
    pending_invoice.save(update_fields=["provider", "fiscal_payload", "updated_at"])

    response = api_client.post(f"/api/v1/invoices/{pending_invoice.id}/refresh-status/", {}, format="json")

    assert response.status_code == 200, response.data
    assert _fiscal_jobs(pending_invoice.order).count() == 1
    # O PDV decide pela resposta se ja existe cupom para imprimir. Sem estes
    # dois campos a nota voltava autorizada e a tela continuava tratando como
    # "nao imprimivel" — o operador tinha de mandar imprimir na mao.
    assert response.data["fiscal_state"] == "authorized"
    assert response.data["printable"] is True


def test_terminal_que_espera_o_cupom_marca_o_trabalho_como_manual(
    account, pending_invoice, printer, api_client
):
    """O PDV avisa que vai imprimir, e o agente local nao pega o mesmo cupom.

    A consulta pode ser o instante em que a nota autoriza. O cupom criado ali
    ia para o laco automatico do agente, que imprimia a via ANTES de o terminal
    pedir a dele — o cliente recebia dois DANFEs da mesma venda.
    """
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    pending_invoice.provider = _AuthorizesOnRetryProvider.name
    pending_invoice.fiscal_payload = {**pending_invoice.fiscal_payload, "awaiting": "authorization"}
    pending_invoice.save(update_fields=["provider", "fiscal_payload", "updated_at"])

    response = api_client.post(
        f"/api/v1/invoices/{pending_invoice.id}/refresh-status/",
        {"manual_print": True},
        format="json",
    )

    assert response.status_code == 200, response.data
    job = _fiscal_jobs(pending_invoice.order).get()
    assert job.payload["manual_only"] is True


def test_autorizacao_sem_ninguem_esperando_continua_automatica(
    account, pending_invoice, printer, api_client
):
    """Webhook e reprocessamento nao tem terminal na frente do cliente.

    Marcar o trabalho como manual ali deixaria a autorizacao que chega horas
    depois sem sair em impressora nenhuma.
    """
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    pending_invoice.provider = _AuthorizesOnRetryProvider.name
    pending_invoice.fiscal_payload = {**pending_invoice.fiscal_payload, "awaiting": "authorization"}
    pending_invoice.save(update_fields=["provider", "fiscal_payload", "updated_at"])

    response = api_client.post(
        f"/api/v1/invoices/{pending_invoice.id}/refresh-status/", {}, format="json"
    )

    assert response.status_code == 200, response.data
    job = _fiscal_jobs(pending_invoice.order).get()
    assert job.payload["manual_only"] is False


def test_the_danfe_is_never_printed_twice(pending_invoice, printer, manager_user):
    """Varios caminhos chamam o mesmo enfileiramento; o cupom sai uma vez so."""
    reprocess_pending_fiscal_invoices()
    pending_invoice.refresh_from_db()

    ensure_fiscal_print_job(pending_invoice, user=manager_user)
    ensure_fiscal_print_job(pending_invoice, user=manager_user)

    assert _fiscal_jobs(pending_invoice.order).count() == 1


def test_a_printer_failure_does_not_undo_the_authorization(
    pending_invoice, manager_user
):
    """Sem impressora cadastrada, a autorizacao continua valendo."""
    retried, issued = reprocess_pending_fiscal_invoices()
    pending_invoice.refresh_from_db()

    assert (retried, issued) == (1, 1)
    assert pending_invoice.status == Invoice.STATUS_ISSUED
    assert not _fiscal_jobs(pending_invoice.order).exists()


def test_a_note_that_is_still_pending_never_gets_a_danfe(pending_invoice, printer):
    """O guarda continua sendo a autorizacao, nao a passagem pela funcao."""
    assert ensure_fiscal_print_job(pending_invoice) is None
    assert not _fiscal_jobs(pending_invoice.order).exists()


# ------------------------------------------------- consulta de situacao

def test_refresh_refuses_when_no_provider_transmits(
    account, pending_invoice, fiscal_config, api_client
):
    """A consulta deixou de fingir que consultou.

    `invoice.provider` so e gravado quando a emissao chega ao provedor. Com o
    campo vazio, `get_provider("")` devolvia o provedor Manual, cujo `status()`
    apenas repete o que ja estava no banco: a API respondia 200 sem ter falado
    com ninguem. Agora recusa com o motivo.
    """
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    pending_invoice.provider = ""
    pending_invoice.save(update_fields=["provider", "updated_at"])
    fiscal_config.provider = "manual"
    fiscal_config.save(update_fields=["provider", "updated_at"])

    response = api_client.post(
        f"/api/v1/invoices/{pending_invoice.id}/refresh-status/", {}, format="json"
    )

    assert response.status_code == 400, response.data
    assert "nunca foi transmitida" in " ".join(response.data["detail"])


def test_refresh_uses_the_configured_provider_when_the_field_is_empty(
    account, pending_invoice, printer, api_client
):
    """Campo vazio numa nota que ja foi transmitida cai na config, nao no Manual."""
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    pending_invoice.provider = ""
    pending_invoice.fiscal_payload = {**pending_invoice.fiscal_payload, "awaiting": "authorization"}
    pending_invoice.save(update_fields=["provider", "fiscal_payload", "updated_at"])

    response = api_client.post(
        f"/api/v1/invoices/{pending_invoice.id}/refresh-status/", {}, format="json"
    )

    assert response.status_code == 200, response.data
    pending_invoice.refresh_from_db()
    # A config aponta para um provider que transmite: a consulta aconteceu.
    assert pending_invoice.status == Invoice.STATUS_ISSUED
    assert _fiscal_jobs(pending_invoice.order).count() == 1


@register_provider
class _NotFoundOnStatusProvider(FiscalProvider):
    """O provedor nao conhece a referencia consultada."""

    name = "test_status_not_found"
    transmits = True

    def emit(self, invoice, config):
        raise FiscalUnavailable("SEFAZ indisponivel (simulado)")

    def status(self, invoice):
        raise FiscalNotFound("Nenhum documento com esta referencia (simulado).")


def test_a_consult_that_finds_nothing_releases_the_note_for_retransmission(
    pending_invoice, fiscal_config, manager_user
):
    """404 na consulta nao e recusa: e "o documento nao esta aqui".

    Tratar como rejeicao marcaria como recusada justamente a nota que nao
    conseguiu ser transmitida. E, para uma nota presa em reconciliacao, esta e
    a unica resposta que libera a retransmissao com seguranca — se o provedor
    nao tem o documento, reenviar nao duplica nada.
    """
    fiscal_config.provider = _NotFoundOnStatusProvider.name
    fiscal_config.save(update_fields=["provider", "updated_at"])
    pending_invoice.provider = ""
    pending_invoice.fiscal_payload = {**pending_invoice.fiscal_payload, "awaiting": "reconciliation"}
    pending_invoice.save(update_fields=["provider", "fiscal_payload", "updated_at"])

    refreshed = refresh_fiscal_invoice_status(pending_invoice, user=manager_user)

    assert refreshed.status == Invoice.STATUS_PENDING
    assert refreshed.fiscal_payload["awaiting"] == "transmission"
