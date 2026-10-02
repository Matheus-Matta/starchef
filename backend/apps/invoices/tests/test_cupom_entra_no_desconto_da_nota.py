"""O cupom é desconto na NFC-e.

Produção, 01/10/2026: "Nota fiscal não emitida: total fiscal inconsistente; o
valor total deve corresponder a produtos - desconto + outras despesas" — "às
vezes ia e às vezes não": falhava sempre que a venda tinha cupom.

O total do pedido abate `discount` E `coupon_discount`, mas a nota registrava
como desconto só o `discount`. Produtos R$ 50, cupom R$ 5, total R$ 45: a nota
dizia desconto zero, a conta não fechava, e a conferência recusava antes de a
nota sair para a Focus.
"""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FocusNfeProvider, ManualFiscalProvider
from apps.invoices.services import billable_order_items, emit_fiscal_invoice
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db


@pytest.fixture
def venda_com_cupom(account, restaurant, branch, manager_user):
    FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        provider=ManualFiscalProvider.name, cnpj="11222333000181", uf="SP",
        environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
        corporate_name="Loja Teste LTDA",
    )
    produto = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("25.00"),
    )
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=2, user=manager_user)
    # O que `recalculate_order` grava com um cupom de R$ 5 e R$ 2 de desconto.
    Order.all_objects.filter(pk=pedido.pk).update(
        discount=Decimal("2.00"), coupon_discount=Decimal("5.00"), total=Decimal("43.00"),
    )
    pedido.refresh_from_db()
    return pedido, manager_user


def test_cupom_soma_ao_desconto_da_nota(venda_com_cupom):
    pedido, usuario = venda_com_cupom

    emit_fiscal_invoice(pedido, user=usuario)
    nota = Invoice.all_objects.get(order=pedido)

    assert nota.products_total == Decimal("50.00")
    assert nota.discount_total == Decimal("7.00")
    assert nota.total_amount == Decimal("43.00")


def test_nota_com_cupom_passa_na_conferencia_da_focus(venda_com_cupom):
    """A conferência que recusava a venda em produção."""
    pedido, usuario = venda_com_cupom

    emit_fiscal_invoice(pedido, user=usuario)
    nota = Invoice.all_objects.get(order=pedido)

    with tenant_context(pedido.account):
        outras_despesas = FocusNfeProvider._validate_totals(nota, billable_order_items(pedido))
    assert outras_despesas == Decimal("0.00")
