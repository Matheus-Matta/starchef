"""O extrato da sessão traz o total de cada forma de pagamento e o total geral.

O detalhe da sessão listava recebimento por recebimento. Para fechar o dia, o
gerente somava de cabeça "quanto deu no PIX, quanto no crédito" para bater com
a maquininha e o extrato do banco. O servidor soma — em `Decimal`, a partir dos
valores já gravados — e a tela só mostra.
"""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.cash_session_statement import cash_session_statement
from apps.payments.models import PaymentMethod
from apps.payments.services import open_cash_register, register_payment

pytestmark = pytest.mark.django_db


def _forma(account, restaurant, branch, nome, tipo):
    return PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch, name=nome, method_type=tipo
    )


@pytest.fixture
def extrato(account, restaurant, branch, admin_user):
    with tenant_context(account):
        sessao = open_cash_register(
            restaurant=restaurant, branch=branch, user=admin_user, opening_amount=Decimal("50.00")
        )
        produto = Product.objects.create(
            account=account, restaurant=restaurant, branch=branch, name="Prato",
            internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("10.05"),
        )
        dinheiro = _forma(account, restaurant, branch, "Dinheiro", PaymentMethod.TYPE_CASH)
        pix = _forma(account, restaurant, branch, "PIX", "pix")

        def vender(forma, valor):
            pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                                  user=admin_user)
            add_order_item(order=pedido, product=produto, quantity=1, user=admin_user)
            pedido.refresh_from_db()
            register_payment(order=pedido, user=admin_user, payment_method_id=forma.pk,
                             amount=Decimal(valor), cash_register_id=sessao.pk)

        vender(dinheiro, "20.00")  # R$ 10,05 de conta: R$ 9,95 de troco
        vender(pix, "10.05")
        vender(pix, "10.05")
        sessao.refresh_from_db()
        return cash_session_statement(sessao)


def _por_nome(extrato):
    return {linha["payment_method_name"]: linha for linha in extrato["payment_totals"]}


def test_cada_forma_tem_o_proprio_total_e_quantidade(extrato):
    totais = _por_nome(extrato)

    assert totais["PIX"]["amount"] == "20.10"
    assert totais["PIX"]["count"] == 2
    # O dinheiro conta o que FICOU, não a nota que o cliente entregou.
    assert totais["Dinheiro"]["amount"] == "10.05"
    assert totais["Dinheiro"]["count"] == 1


def test_o_total_geral_soma_todas_as_formas(extrato):
    assert extrato["payments_total"] == "30.15"
    assert extrato["payments_count"] == 3


def test_o_troco_que_saiu_aparece_ao_lado(extrato):
    assert _por_nome(extrato)["Dinheiro"]["change"] == "9.95"
