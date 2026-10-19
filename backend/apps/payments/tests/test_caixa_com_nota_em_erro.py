"""Venda paga com a NFC-e recusada CONTA no fechamento do caixa.

O dinheiro entrou na gaveta e o PIX caiu na conta: a recusa da SEFAZ é um
problema do documento fiscal, a corrigir e reenviar, e não desfaz a venda. Se
o fechamento olhasse a nota, o caixa fecharia com "sobra" do valor exato das
vendas com nota em erro — e o operador seria cobrado por uma diferença que não
existe. O fechamento soma os RECEBIMENTOS da sessão; isto fixa que nenhuma
regra fiscal entre nessa conta.
"""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.invoices.models import Invoice
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import CashRegister, PaymentMethod
from apps.payments.serializers import CashRegisterSerializer
from apps.payments.services import register_payment
from apps.printers.cash_document_totals import gaveta, vendas_por_forma

pytestmark = pytest.mark.django_db


@pytest.fixture
def turno(account, restaurant, branch, manager_user):
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    sessao = CashRegister.objects.create(
        account=account, restaurant=restaurant, branch=branch, opened_by=manager_user,
        opening_amount="100.00", expected_amount="100.00",
        created_by=manager_user, updated_by=manager_user,
    )
    produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     name="Prato", internal_code=f"P{uuid.uuid4().hex[:6]}",
                                     sale_price=Decimal("40.00"))

    def forma(tipo):
        return PaymentMethod.objects.create(account=account, restaurant=restaurant, branch=branch,
                                            name=tipo, method_type=tipo)

    def vender(metodo, *, recebido, nota):
        pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                              user=manager_user)
        add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
        pedido.refresh_from_db()
        register_payment(order=pedido, user=manager_user, payment_method_id=metodo.pk,
                         amount=recebido, cash_register_id=sessao.pk)
        if nota:
            Invoice.objects.create(account=account, restaurant=restaurant, branch=branch,
                                   order=pedido, status=nota, number="7", series=1,
                                   error_message="ACBrLib: SEFAZ recusou a nota — 386 Rejeicao")
        return pedido

    return sessao, forma, vender


def test_venda_com_nota_recusada_entra_nas_vendas_e_na_gaveta(turno):
    sessao, forma, vender = turno
    dinheiro, pix = forma(PaymentMethod.TYPE_CASH), forma(PaymentMethod.TYPE_PIX)
    vender(dinheiro, recebido="50.00", nota=Invoice.STATUS_ERROR)   # troco de 10
    vender(pix, recebido="40.00", nota=Invoice.STATUS_ERROR)
    vender(dinheiro, recebido="40.00", nota=Invoice.STATUS_ISSUED)  # a de controle

    with tenant_context(sessao.account):
        sessao.refresh_from_db()
        por_forma = vendas_por_forma(sessao)
        na_gaveta = gaveta(sessao)
        vendas = CashRegisterSerializer().get_sales(sessao)

    assert por_forma["total"] == 120_00          # 40 + 40 + 40, todas
    assert por_forma["dinheiro"] == 80_00
    assert na_gaveta["vendas"] == 80_00
    assert len(vendas) == 3


def test_venda_sem_nota_nenhuma_tambem_conta(turno):
    """Restaurante sem NFC-e, ou a nota que ainda não saiu da fila."""
    sessao, forma, vender = turno
    vender(forma(PaymentMethod.TYPE_PIX), recebido="40.00", nota=None)

    with tenant_context(sessao.account):
        assert vendas_por_forma(sessao)["total"] == 40_00
