"""O cancelamento encerra também o estado financeiro do pedido."""

import importlib
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import connection

from apps.core.tenant import tenant_context
from apps.orders.models import Order
from apps.orders.services import add_order_item, cancel_order, close_order, create_order
from apps.payments.models import Payment, PaymentMethod
from apps.payments.services import cancel_payment, register_payment


pytestmark = pytest.mark.django_db


def test_pedido_cancelado_deixa_de_aguardar_pagamento(account, restaurant, branch, manager_user):
    """O pedido cancelado aparecia como pendente no filtro de pagamento."""
    pedido = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user
    )

    cancel_order(pedido, manager_user, reason="Cliente desistiu")

    with tenant_context(account):
        pedido.refresh_from_db()
        assert pedido.status == Order.STATUS_CANCELLED
        assert pedido.payment_status == Order.PAYMENT_CANCELLED
        assert not Order.objects.filter(pk=pedido.pk, payment_status=Order.PAYMENT_PENDING).exists()


def test_cancelar_pedido_parcial_cancela_recebimento_e_caixa(
    account, restaurant, branch, produto, manager_user
):
    """Um pagamento parcial não pode continuar aprovado após cancelar a venda."""
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    pedido = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user
    )
    add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
    metodo = PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Dinheiro", method_type=PaymentMethod.TYPE_CASH,
    )
    pedido = close_order(pedido, manager_user)
    recebimento = register_payment(
        order=pedido, user=manager_user, payment_method_id=metodo.pk,
        amount=Decimal("5.00"),
    )

    cancel_order(pedido, manager_user, reason="Cliente desistiu")

    with tenant_context(account):
        pedido.refresh_from_db()
        recebimento.refresh_from_db()
        assert pedido.status == Order.STATUS_CANCELLED
        assert pedido.payment_status == Order.PAYMENT_CANCELLED
        assert recebimento.status == Payment.STATUS_CANCELLED
        assert not recebimento.cash_movements.filter(status="approved").exists()


def test_cancelar_pedido_pago_marca_reembolso_sem_estornar_recebimento(
    account, restaurant, branch, produto, manager_user
):
    """O estado avisa sobre reembolso sem executar um estorno financeiro agora."""
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    pedido = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user
    )
    add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
    metodo = PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Dinheiro pago", method_type=PaymentMethod.TYPE_CASH,
    )
    pedido = close_order(pedido, manager_user)
    recebimento = register_payment(
        order=pedido, user=manager_user, payment_method_id=metodo.pk,
        amount=pedido.total,
    )

    cancel_order(pedido, manager_user, reason="Cliente desistiu")
    cancel_order(pedido, manager_user, reason="Cliente desistiu")

    with tenant_context(account):
        pedido.refresh_from_db()
        recebimento.refresh_from_db()
        assert pedido.status == Order.STATUS_CANCELLED
        assert pedido.payment_status == Order.PAYMENT_REFUNDED
        assert recebimento.status == Payment.STATUS_APPROVED

    with pytest.raises(ValidationError, match="cancelado"):
        cancel_payment(payment=recebimento, user=manager_user)


def test_migracao_corrige_estados_de_pedidos_ja_cancelados(
    account, restaurant, branch, manager_user
):
    """Pedidos antigos não devem continuar no filtro de pagamento pendente."""
    with tenant_context(account):
        pendente = create_order(
            restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user
        )
        pendente.status = Order.STATUS_CANCELLED
        pendente.save(update_fields=["status"])
        pago = create_order(
            restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user
        )
        pago.status = Order.STATUS_CANCELLED
        pago.payment_status = Order.PAYMENT_PAID
        pago.save(update_fields=["status", "payment_status"])
        metodo = PaymentMethod.objects.create(
            account=account, restaurant=restaurant, branch=branch,
            name="Dinheiro legado", method_type=PaymentMethod.TYPE_CASH,
        )
        recebimento = Payment.objects.create(
            account=account, restaurant=restaurant, branch=branch,
            order=pago, payment_method=metodo, amount=Decimal("10.00"),
        )

        migracao = importlib.import_module("apps.orders.migrations.0010_alter_order_payment_status")
        migracao.encerrar_pagamentos_de_pedidos_cancelados(
            django_apps, SimpleNamespace(connection=connection)
        )

        pendente.refresh_from_db()
        pago.refresh_from_db()
        recebimento.refresh_from_db()
        assert pendente.payment_status == Order.PAYMENT_CANCELLED
        assert pago.payment_status == Order.PAYMENT_REFUNDED
        assert recebimento.status == Payment.STATUS_APPROVED
