import pytest
from django.core.exceptions import ValidationError

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FiscalProvider, register_provider
from apps.invoices.services import emit_fiscal_invoice
from apps.orders.models import Order
from apps.orders.services import cancel_order, create_order

pytestmark = pytest.mark.django_db


@register_provider
class _OrderCancellationProvider(FiscalProvider):
    name = "test_order_cancellation"
    transmits = True
    cancellations = 0

    def cancel(self, invoice, reason):
        type(self).cancellations += 1
        invoice.status = Invoice.STATUS_CANCELLED
        return invoice


@pytest.fixture(autouse=True)
def _reset_provider():
    _OrderCancellationProvider.cancellations = 0


@pytest.fixture
def fiscal_config(account, restaurant, branch):
    return FiscalConfig.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        provider=_OrderCancellationProvider.name,
        cnpj="11222333000181",
        uf="SP",
    )


def _invoice(account, restaurant, branch, user, status):
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=user,
    )
    return Invoice.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        order=order,
        provider=_OrderCancellationProvider.name,
        status=status,
    )


def test_cancelar_pedido_cancela_a_nota_autorizada(
    account, restaurant, branch, manager_user, fiscal_config
):
    """O pedido cancelado não pode continuar com uma nota viva na SEFAZ."""
    invoice = _invoice(account, restaurant, branch, manager_user, Invoice.STATUS_ISSUED)

    order = cancel_order(invoice.order, manager_user, "Venda cancelada")

    invoice.refresh_from_db()
    assert order.status == Order.STATUS_CANCELLED
    assert invoice.status == Invoice.STATUS_CANCELLED
    assert _OrderCancellationProvider.cancellations == 1


def test_cancelar_pedido_descarta_a_nota_pendente(
    account, restaurant, branch, manager_user, fiscal_config
):
    """Uma nota pendente do pedido cancelado não pode ser emitida depois."""
    invoice = _invoice(account, restaurant, branch, manager_user, Invoice.STATUS_PENDING)

    cancel_order(invoice.order, manager_user, "Venda cancelada")

    invoice.refresh_from_db()
    assert invoice.status == Invoice.STATUS_CANCELLED
    assert "awaiting" not in invoice.fiscal_payload


def test_pedido_cancelado_nao_pode_emitir_nova_nota(
    restaurant, branch, manager_user, fiscal_config
):
    """Nenhum caminho posterior pode transformar o cancelamento em emissão."""
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=manager_user,
    )
    order.status = Order.STATUS_CANCELLED
    order.save(update_fields=["status", "updated_at"])

    with pytest.raises(ValidationError, match="Pedido cancelado"):
        emit_fiscal_invoice(order, user=manager_user)
