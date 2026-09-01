"""Nota fiscal automatica no pagamento (`order_fully_paid`).

O que se garante aqui: quitar o pedido emite a NFC-e e manda recibo e DANFE
para a impressora, sem ninguem clicar em nada — e, principalmente, que nada
disso pode derrubar um recebimento que ja foi gravado.
"""
import uuid
from decimal import Decimal

import pytest

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FiscalProvider, FiscalUnavailable, register_provider
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import PaymentMethod
from apps.payments.services import register_payment
from apps.printers.models import PrintJob, Printer

pytestmark = pytest.mark.django_db


@register_provider
class _AutoIssueProvider(FiscalProvider):
    """Autoriza na hora, como um provedor real com SEFAZ no ar."""

    name = "test_auto_issue"
    transmits = True

    def emit(self, invoice, config):
        invoice.provider = self.name
        invoice.status = Invoice.STATUS_ISSUED
        invoice.authorization_protocol = "135260000000001"
        return invoice

    def cancel(self, invoice, reason):
        invoice.status = Invoice.STATUS_CANCELLED
        return invoice

    def status(self, invoice):
        return invoice.status


@register_provider
class _UnavailableProvider(FiscalProvider):
    """SEFAZ/integrador fora do ar no momento do pagamento."""

    name = "test_auto_issue_unavailable"
    transmits = True

    def emit(self, invoice, config):
        raise FiscalUnavailable("SEFAZ indisponivel (simulado)")


@pytest.fixture
def product(account, restaurant, branch):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("25.00"),
    )


@pytest.fixture(autouse=True)
def _no_cash_register_required(restaurant):
    """O recorte destes testes e o fiscal, nao a gaveta.

    Exigir caixa aberto acrescentaria uma sessao a cada cenario sem mudar nada
    do que se quer provar aqui.
    """
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    return restaurant


@pytest.fixture
def order(restaurant, branch, product, manager_user):
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    order.refresh_from_db()
    return order


@pytest.fixture
def cash_method(account, restaurant, branch, manager_user):
    return PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Dinheiro",
        method_type=PaymentMethod.TYPE_CASH, created_by=manager_user, updated_by=manager_user,
    )


@pytest.fixture
def printer(account, restaurant, branch, manager_user):
    return Printer.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Caixa",
        auto_print=True, created_by=manager_user, updated_by=manager_user,
    )


@pytest.fixture
def fiscal_config(account, restaurant, branch):
    return FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        provider=_AutoIssueProvider.name, cnpj="11222333000181", uf="SP",
        environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
    )


def _pay(order, method, user, amount=None):
    return register_payment(
        order=order, user=user, payment_method_id=method.id,
        amount=amount if amount is not None else order.total,
    )


def test_full_payment_issues_the_invoice(
    django_capture_on_commit_callbacks, order, cash_method, manager_user, printer, fiscal_config
):
    with django_capture_on_commit_callbacks(execute=True):
        _pay(order, cash_method, manager_user)

    invoice = Invoice.all_objects.get(order=order)
    assert invoice.status == Invoice.STATUS_ISSUED
    assert invoice.access_key


def test_full_payment_prints_receipt_and_danfe_on_the_resolved_printer(
    django_capture_on_commit_callbacks, order, cash_method, manager_user, printer, fiscal_config
):
    with django_capture_on_commit_callbacks(execute=True):
        _pay(order, cash_method, manager_user)

    jobs = {job.job_type: job for job in PrintJob.all_objects.filter(order=order)}
    assert set(jobs) == {PrintJob.TYPE_RECEIPT, PrintJob.TYPE_FISCAL}
    # Sem impressora no trabalho, o agente local pula o cupom e a nota nunca sai.
    assert {job.printer_id for job in jobs.values()} == {printer.id}


def test_unauthorized_invoice_prints_the_receipt_but_not_the_danfe(
    django_capture_on_commit_callbacks, order, cash_method, manager_user, printer, fiscal_config
):
    """O cliente nao pode receber um DANFE cuja chave nao existe na SEFAZ.

    A venda ja esta paga e o recibo sai normalmente; o cupom fiscal so sai
    quando (e se) a autorizacao chegar.
    """
    fiscal_config.provider = _UnavailableProvider.name
    fiscal_config.save(update_fields=["provider", "updated_at"])

    with django_capture_on_commit_callbacks(execute=True):
        _pay(order, cash_method, manager_user)

    invoice = Invoice.all_objects.get(order=order)
    assert invoice.status == Invoice.STATUS_PENDING
    assert [job.job_type for job in PrintJob.all_objects.filter(order=order)] == [PrintJob.TYPE_RECEIPT]


def test_partial_payment_issues_nothing(
    django_capture_on_commit_callbacks, order, cash_method, manager_user, printer, fiscal_config
):
    with django_capture_on_commit_callbacks(execute=True):
        _pay(order, cash_method, manager_user, amount=Decimal("1.00"))

    assert not Invoice.all_objects.filter(order=order).exists()
    assert not PrintJob.all_objects.filter(order=order).exists()


def test_restaurant_without_fiscal_config_still_prints_the_receipt(
    django_capture_on_commit_callbacks, order, cash_method, manager_user, printer
):
    # Nao emitir NFC-e e uma escolha valida do restaurante, nao uma falha: a
    # venda continua imprimindo o recibo.
    with django_capture_on_commit_callbacks(execute=True):
        _pay(order, cash_method, manager_user)

    assert not Invoice.all_objects.filter(order=order).exists()
    assert [job.job_type for job in PrintJob.all_objects.filter(order=order)] == [PrintJob.TYPE_RECEIPT]


def test_payment_survives_a_restaurant_without_any_printer(
    django_capture_on_commit_callbacks, order, cash_method, manager_user, fiscal_config
):
    # Nenhuma impressora cadastrada: `resolve_printer_for` recusa, e o
    # recebimento ja commitado nao pode ser derrubado por isso.
    with django_capture_on_commit_callbacks(execute=True):
        payment = _pay(order, cash_method, manager_user)

    order.refresh_from_db()
    assert order.payment_status == Order.PAYMENT_PAID
    assert payment.pk is not None
    assert Invoice.all_objects.filter(order=order).exists()
    assert not PrintJob.all_objects.filter(order=order).exists()


def test_receipt_is_not_printed_twice_when_the_pdv_already_printed(
    django_capture_on_commit_callbacks, order, cash_method, manager_user, printer, fiscal_config
):
    # O PDV imprime o proprio recibo ao concluir a venda; a impressao
    # automatica nao pode fazer sair um segundo cupom da mesma venda.
    from apps.printers.services import register_print_job

    register_print_job(order=order, user=manager_user, job_type=PrintJob.TYPE_RECEIPT)
    with django_capture_on_commit_callbacks(execute=True):
        _pay(order, cash_method, manager_user)

    assert PrintJob.all_objects.filter(order=order, job_type=PrintJob.TYPE_RECEIPT).count() == 1


def test_pdv_printing_claims_the_automatic_job_instead_of_duplicating_it(
    django_capture_on_commit_callbacks, order, cash_method, manager_user, printer, fiscal_config
):
    """O cupom do cliente sai uma vez so.

    A emissao automatica ja criou recibo e DANFE; quando o terminal pede para
    imprimir logo depois, e o MESMO documento. Antes saiam duas vias em quem
    tem impressao automatica ligada na impressora do caixa.
    """
    from apps.invoices.services import print_fiscal_invoice
    from apps.printers.services import register_print_job

    with django_capture_on_commit_callbacks(execute=True):
        _pay(order, cash_method, manager_user)
    invoice = Invoice.all_objects.get(order=order)

    receipt = register_print_job(
        order=order, user=manager_user, job_type=PrintJob.TYPE_RECEIPT, manual_only=True
    )
    danfe = print_fiscal_invoice(invoice, user=manager_user, printer=printer, manual_only=True)

    assert PrintJob.all_objects.filter(order=order).count() == 2
    # O terminal assume os dois: `manual_only` tira o trabalho do laco do agente.
    assert receipt.payload["manual_only"] is True
    assert danfe.payload["manual_only"] is True


def test_reprinting_an_already_printed_receipt_creates_a_new_job(
    django_capture_on_commit_callbacks, order, cash_method, manager_user, printer, fiscal_config
):
    from apps.printers.services import register_print_job

    with django_capture_on_commit_callbacks(execute=True):
        _pay(order, cash_method, manager_user)
    printed = PrintJob.all_objects.get(order=order, job_type=PrintJob.TYPE_RECEIPT)
    printed.status = PrintJob.STATUS_PRINTED
    printed.save(update_fields=["status"])

    reprint = register_print_job(
        order=order, user=manager_user, job_type=PrintJob.TYPE_RECEIPT, manual_only=True
    )

    assert reprint.pk != printed.pk


# --------------------------------------------------------- PDV desktop


def _desktop_terminal(account, restaurant):
    from apps.payments.models import PdvTerminal

    return PdvTerminal.objects.create(
        account=account, restaurant=restaurant,
        installation_id=f"desktop-{uuid.uuid4().hex[:8]}",
        device_type=PdvTerminal.TYPE_DESKTOP, role=PdvTerminal.ROLE_PRINCIPAL,
    )


def _web_terminal(account, restaurant):
    from apps.payments.models import PdvTerminal

    return PdvTerminal.objects.create(
        account=account, restaurant=restaurant,
        installation_id=f"web-{uuid.uuid4().hex[:8]}",
        device_type=PdvTerminal.TYPE_WEB, role=PdvTerminal.ROLE_WEB,
    )


def test_desktop_payment_emits_the_invoice_but_does_not_print_automatically(
    django_capture_on_commit_callbacks, account, restaurant, order, cash_method, manager_user, printer, fiscal_config
):
    """O gesto de imprimir e do terminal (`_completePaidOrder`), nao do pagamento.

    Sem isto, o cupom e o DANFE saiam automaticamente assim que o ULTIMO
    pagamento era registrado — quase sempre antes do operador clicar em
    "Concluir pedido". O terminal repetia a impressao ao clicar e, se o job
    automatico ja tivesse sido entregue pelo agente local, a segunda tentativa
    nao encontrava mais nada para reaproveitar e criava um cupom NOVO: duas
    vias fisicas da mesma venda.
    """
    terminal = _desktop_terminal(account, restaurant)

    with django_capture_on_commit_callbacks(execute=True):
        register_payment(
            order=order, user=manager_user, payment_method_id=cash_method.id,
            amount=order.total, terminal=terminal,
        )

    invoice = Invoice.all_objects.get(order=order)
    assert invoice.status == Invoice.STATUS_ISSUED
    assert not PrintJob.all_objects.filter(order=order).exists()


def test_web_payment_does_not_send_paper_to_the_counter_printer(
    django_capture_on_commit_callbacks, account, restaurant, order, cash_method, manager_user, printer, fiscal_config
):
    """A web imprime no navegador de quem fechou a venda, nao no caixa.

    Um PrintJob nascido aqui iria para a fila do agente local — a impressora
    do balcao — por causa de uma venda que pode ter sido fechada por alguem na
    retaguarda, longe dela.
    """
    terminal = _web_terminal(account, restaurant)

    with django_capture_on_commit_callbacks(execute=True):
        register_payment(
            order=order, user=manager_user, payment_method_id=cash_method.id,
            amount=order.total, terminal=terminal,
        )

    assert Invoice.all_objects.get(order=order).status == Invoice.STATUS_ISSUED
    assert not PrintJob.all_objects.filter(order=order).exists()


def test_payment_without_an_identified_terminal_still_prints(
    django_capture_on_commit_callbacks, order, cash_method, manager_user, printer, fiscal_config
):
    """Integracao ou cliente antigo nao tem para onde devolver o documento.

    Sem terminal identificado ninguem vai imprimir por conta propria depois —
    a venda ficaria sem cupom nenhum.
    """
    with django_capture_on_commit_callbacks(execute=True):
        _pay(order, cash_method, manager_user)

    jobs = {job.job_type for job in PrintJob.all_objects.filter(order=order)}
    assert jobs == {PrintJob.TYPE_RECEIPT, PrintJob.TYPE_FISCAL}


def test_desktop_terminal_prints_both_documents_once_when_the_operator_concludes(
    django_capture_on_commit_callbacks, account, restaurant, order, cash_method, manager_user, printer, fiscal_config
):
    """Simula o clique em "Concluir pedido": os dois documentos saem, uma vez so."""
    from apps.invoices.services import print_fiscal_invoice
    from apps.printers.services import register_print_job

    terminal = _desktop_terminal(account, restaurant)
    with django_capture_on_commit_callbacks(execute=True):
        register_payment(
            order=order, user=manager_user, payment_method_id=cash_method.id,
            amount=order.total, terminal=terminal,
        )
    invoice = Invoice.all_objects.get(order=order)
    assert not PrintJob.all_objects.filter(order=order).exists()

    receipt = register_print_job(
        order=order, user=manager_user, job_type=PrintJob.TYPE_RECEIPT,
        printer=printer, manual_only=True,
    )
    danfe = print_fiscal_invoice(invoice, user=manager_user, printer=printer, manual_only=True)

    jobs = list(PrintJob.all_objects.filter(order=order))
    assert len(jobs) == 2
    assert {job.pk for job in jobs} == {receipt.pk, danfe.pk}
