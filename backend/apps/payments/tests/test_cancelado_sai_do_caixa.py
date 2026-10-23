"""Pedido PAGO e depois cancelado sai do caixa — e da gaveta, se foi dinheiro.

O cancelamento de um pedido totalmente pago só marcava o pedido como
"estornado": os recebimentos seguiam aprovados. O fechamento somava a venda
desfeita (R$ 50 cancelado + R$ 20 pago davam R$ 70 no crédito) e, no dinheiro,
o esperado da gaveta cobrava do operador a nota que ele devolveu ao cliente.
"""
import uuid
from decimal import Decimal

import pytest
from django.db.models import Sum

from apps.core.tenant import tenant_context
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, cancel_order, create_order
from apps.payments.cash_session_statement import cash_session_statement
from apps.payments.models import Payment, PaymentMethod
from apps.payments.services import open_cash_register, register_payment

pytestmark = pytest.mark.django_db


@pytest.fixture
def caixa(account, restaurant, branch, admin_user):
    with tenant_context(account):
        sessao = open_cash_register(
            restaurant=restaurant, branch=branch, user=admin_user, opening_amount=Decimal("100.00")
        )

    def forma(nome, tipo):
        return PaymentMethod.objects.create(
            account=account, restaurant=restaurant, branch=branch, name=nome, method_type=tipo
        )

    def vender(forma_de_pagamento, valor):
        produto = Product.objects.create(
            account=account, restaurant=restaurant, branch=branch, name="Prato",
            internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal(valor),
        )
        pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                              user=admin_user)
        add_order_item(order=pedido, product=produto, quantity=1, user=admin_user)
        pedido.refresh_from_db()
        recebimento = register_payment(order=pedido, user=admin_user, payment_method_id=forma_de_pagamento.pk,
                                       amount=Decimal(valor), cash_register_id=sessao.pk,
                                       metadata={"card_subtype": "credit"}
                                       if forma_de_pagamento.method_type == "card" else None)
        return pedido, recebimento

    def gaveta():
        return sessao.movements.filter(status="approved").aggregate(v=Sum("amount"))["v"]

    def extrato():
        sessao.refresh_from_db()
        return {linha["payment_method_name"]: linha for linha in cash_session_statement(sessao)["payment_totals"]}

    # As consultas do teste também passam pelo filtro de conta.
    with tenant_context(account):
        yield {"forma": forma, "vender": vender, "gaveta": gaveta, "extrato": extrato, "user": admin_user}


def test_pedido_pago_cancelado_nao_soma_no_credito_do_caixa(caixa):
    credito = caixa["forma"]("Crédito", "card")
    cancelado, recebimento = caixa["vender"](credito, "50.00")
    caixa["vender"](credito, "20.00")

    cancel_order(cancelado, caixa["user"], reason="Cliente desistiu")

    assert caixa["extrato"]()["Crédito"]["amount"] == "20.00"
    assert caixa["extrato"]()["Crédito"]["count"] == 1
    recebimento.refresh_from_db()
    # Estornado, não "cancelado": o dinheiro entrou e foi devolvido.
    assert recebimento.status == Payment.STATUS_REFUNDED


def test_pedido_pago_em_dinheiro_cancelado_sai_da_gaveta(caixa):
    dinheiro = caixa["forma"]("Dinheiro", "cash")
    cancelado, _ = caixa["vender"](dinheiro, "30.00")
    assert caixa["gaveta"]() == Decimal("130.00")

    cancel_order(cancelado, caixa["user"], reason="Cliente desistiu")

    # Abertura de R$ 100: os R$ 30 voltaram para o cliente.
    assert caixa["gaveta"]() == Decimal("100.00")
    assert "Dinheiro" not in caixa["extrato"]()


def test_cancelar_duas_vezes_nao_estorna_duas_vezes(caixa):
    dinheiro = caixa["forma"]("Dinheiro", "cash")
    cancelado, _ = caixa["vender"](dinheiro, "30.00")

    cancel_order(cancelado, caixa["user"], reason="Cliente desistiu")
    cancel_order(cancelado, caixa["user"], reason="Cliente desistiu")

    assert caixa["gaveta"]() == Decimal("100.00")
    with tenant_context(cancelado.account):
        cancelado.refresh_from_db()
        assert cancelado.payment_status == Order.PAYMENT_REFUNDED


def test_estorno_aparece_no_extrato_do_caixa(caixa):
    """O estorno não pode só sumir: o gerente confere o que foi devolvido."""
    credito = caixa["forma"]("Crédito", "card")
    cancelado, _ = caixa["vender"](credito, "50.00")
    caixa["vender"](credito, "20.00")

    cancel_order(cancelado, caixa["user"], reason="Cliente desistiu")

    sessao = cancelado.payments.first().cash_movements.first()
    with tenant_context(cancelado.account):
        from apps.payments.models import CashRegister

        extrato = cash_session_statement(CashRegister.objects.get())
    assert extrato["refunds_total"] == "50.00"
    assert [(e["payment_method_name"], e["amount"]) for e in extrato["refunds"]] == [("Crédito", "50.00")]
    assert extrato["refunds"][0]["cancel_reason"] == "Cliente desistiu"
    assert sessao is None  # cartão não mexe na gaveta


def test_estorno_sai_no_relatorio_de_fechamento_impresso(caixa):
    from apps.payments.models import CashRegister
    from apps.printers.cash_documents import closing_text

    caixa["vender"](caixa["forma"]("Crédito", "card"), "20.00")
    cartao, _ = caixa["vender"](caixa["forma"]("Crédito 2", "card"), "50.00")
    dinheiro, _ = caixa["vender"](caixa["forma"]("Dinheiro", "cash"), "30.00")
    cancel_order(cartao, caixa["user"], reason="Cliente desistiu")
    cancel_order(dinheiro, caixa["user"], reason="Cliente desistiu")

    papel = closing_text(CashRegister.objects.get())

    assert "(-) Estornos em dinheiro" in papel
    assert "ESTORNOS (PEDIDOS CANCELADOS)" in papel
    linha_total = next(linha for linha in papel.splitlines() if linha.startswith("Total estornado"))
    assert linha_total.endswith("80.00")
    # As vendas por forma já não contam o que foi devolvido.
    assert next(linha for linha in papel.splitlines() if linha.startswith("Total de vendas")).endswith("20.00")
