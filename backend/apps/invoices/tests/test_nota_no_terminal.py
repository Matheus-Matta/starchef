"""Venda cuja NFC-e é do terminal (`nota_no_terminal`): a nuvem não emite a segunda."""
import pytest

from apps.invoices.models import FiscalConfig
from apps.invoices.services import fiscal_emission_skipped_reason
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.orders.venda_inteira import _nota_no_terminal

pytestmark = pytest.mark.django_db


@pytest.fixture
def pedido(account, restaurant, branch, manager_user):
    FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch, provider="acbrlib", environment="2",
        cnpj="11.222.333/0001-81", corporate_name="Loja", series=1, crt="1",
    )
    return create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)


def test_marca_do_terminal_dispensa_a_emissao_da_nuvem(pedido):
    antes = fiscal_emission_skipped_reason(pedido)
    assert "terminal" not in (antes or "")
    _nota_no_terminal(pedido, {"nota_no_terminal": True})
    pedido.refresh_from_db()
    assert pedido.fiscal_by_terminal is True
    assert fiscal_emission_skipped_reason(pedido) == "A nota desta venda é emitida pelo terminal (StarChef Desktop)."


def test_reenvio_sem_a_marca_nao_desliga(pedido):
    _nota_no_terminal(pedido, {"nota_no_terminal": True})
    _nota_no_terminal(pedido, {})
    _nota_no_terminal(pedido, {"nota_no_terminal": "false"})
    pedido.refresh_from_db()
    assert pedido.fiscal_by_terminal is True


def test_sem_a_marca_a_nuvem_segue_emitindo(pedido):
    _nota_no_terminal(pedido, {"nota_no_terminal": "sim"})  # só o booleano liga
    pedido.refresh_from_db()
    assert pedido.fiscal_by_terminal is False
