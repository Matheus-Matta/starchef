"""O desconto digitado no PDV vai para a NFC-e sem a SEFAZ rejeitar.

A SEFAZ recusa item com desconto maior que o próprio valor (`vDesc > vProd`) e
nota cujo total não bate com produtos - desconto + outras despesas. O rateio
antigo jogava a sobra de centavos no ÚLTIMO item: com um prato de R$ 100 e uma
água de R$ 0,50 no fim, um desconto alto deixava a água com desconto maior que
ela.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.core.tenant import tenant_context
from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FocusNfeProvider, ManualFiscalProvider
from apps.invoices.services import billable_order_items, emit_fiscal_invoice
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, close_order, create_order

pytestmark = pytest.mark.django_db


# Achado por força bruta: 12 em 200 mil vendas aleatórias estouravam no rateio
# antigo — raro, mas é rejeição da SEFAZ com o cliente já pago.
CASO_REAL = (["17.80", "18.30", "19.85", "8.39", "22.53", "0.88"], "87.33")


def _itens(*valores):
    return [SimpleNamespace(pk=i, total_price=Decimal(v)) for i, v in enumerate(valores)]


@pytest.mark.parametrize(
    ("valores", "desconto"),
    [
        (["100.00", "0.50"], "100.40"),
        (["0.01", "33.33", "33.33", "0.02"], "66.68"),
        (["10.00", "10.00", "10.00"], "0.01"),
        (["59.90", "5.00", "0.99"], "65.89"),
        CASO_REAL,
    ],
)
def test_nenhum_item_recebe_desconto_maior_que_ele_e_a_soma_fecha(valores, desconto):
    itens = _itens(*valores)

    rateio = FocusNfeProvider._allocate_discount(itens, Decimal(desconto))

    assert sum(rateio.values()) == Decimal(desconto)
    for item in itens:
        assert Decimal("0.00") <= rateio[item.pk] <= item.total_price, (item.total_price, rateio[item.pk])


def test_o_rateio_antigo_estourava_o_ultimo_item():
    """A prova de que o caso é real: o item de R$ 0,88 levava R$ 0,89."""
    itens = _itens(*CASO_REAL[0])
    antigo = FocusNfeProvider._allocate_total(itens, Decimal(CASO_REAL[1]))

    assert antigo[5] > itens[5].total_price

    novo = FocusNfeProvider._allocate_discount(itens, Decimal(CASO_REAL[1]))
    assert novo[5] <= itens[5].total_price and sum(novo.values()) == Decimal(CASO_REAL[1])


@pytest.fixture
def venda(account, restaurant, branch, manager_user):
    FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        provider=ManualFiscalProvider.name, cnpj="11222333000181", uf="SP",
        environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
        corporate_name="Loja Teste LTDA",
    )
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    for nome, preco in (("Prato", "100.00"), ("Água", "0.50")):
        produto = Product.objects.create(
            account=account, restaurant=restaurant, branch=branch, name=nome,
            internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal(preco),
        )
        add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
    return pedido, manager_user


def test_desconto_digitado_fecha_a_conta_da_nfce(venda):
    pedido, gerente = venda
    pedido = close_order(pedido, gerente, discount="100.40", service_fee_enabled=False)

    emit_fiscal_invoice(pedido, user=gerente)
    nota = Invoice.all_objects.get(order=pedido)
    with tenant_context(pedido.account):
        itens = list(nota.items.all().order_by("line_number"))
        outras = FocusNfeProvider._validate_totals(nota, billable_order_items(pedido))
    rateio = FocusNfeProvider._allocate_discount(itens, nota.discount_total)

    assert (nota.products_total, nota.discount_total, nota.total_amount) == (
        Decimal("100.50"), Decimal("100.40"), Decimal("0.10"),
    )
    liquido = sum(item.total_price - rateio[item.pk] for item in itens)
    assert liquido + outras == nota.total_amount
    assert all(rateio[item.pk] <= item.total_price for item in itens)
