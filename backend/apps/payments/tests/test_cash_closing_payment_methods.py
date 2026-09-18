"""Valores por forma de pagamento no relatório impresso do fechamento."""

import pytest

from apps.core.tenant import tenant_context
from apps.orders.models import Order
from apps.payments.models import CashRegister, Payment, PaymentMethod
from apps.printers.cash_documents import closing_text

pytestmark = pytest.mark.django_db


def test_fechamento_mostra_valor_de_todas_as_formas_principais(
    account, restaurant, branch, admin_user
):
    session = CashRegister.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        opened_by=admin_user,
        opening_amount="100.00",
        expected_amount="100.00",
        created_by=admin_user,
        updated_by=admin_user,
    )
    order = Order.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        sequence=901,
        order_type=Order.TYPE_COUNTER,
        responsible_user=admin_user,
        created_by=admin_user,
        updated_by=admin_user,
    )
    formas = [
        ("Dinheiro", PaymentMethod.TYPE_CASH, "", "10.10"),
        ("Cartao credito", PaymentMethod.TYPE_CARD, Payment.CARD_CREDIT, "20.20"),
        ("Cartao debito", PaymentMethod.TYPE_CARD, Payment.CARD_DEBIT, "30.30"),
        ("PIX", PaymentMethod.TYPE_PIX, "", "40.40"),
        ("Vale/voucher", PaymentMethod.TYPE_VOUCHER, "", "50.50"),
    ]
    for indice, (nome, tipo, subtipo, valor) in enumerate(formas):
        metodo = PaymentMethod.objects.create(
            account=account,
            restaurant=restaurant,
            branch=branch,
            name=f"Metodo {indice}",
            method_type=tipo,
            created_by=admin_user,
            updated_by=admin_user,
        )
        Payment.objects.create(
            account=account,
            restaurant=restaurant,
            branch=branch,
            order=order,
            payment_method=metodo,
            card_subtype=subtipo,
            amount=valor,
            metadata={"cash_register": str(session.pk)},
            created_by=admin_user,
            updated_by=admin_user,
        )

    with tenant_context(account):
        linhas = closing_text(session).splitlines()
    for nome, _, _, valor in formas:
        assert any(linha.startswith(nome) and linha.endswith(valor) for linha in linhas), (nome, linhas)
