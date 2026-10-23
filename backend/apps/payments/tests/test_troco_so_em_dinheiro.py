"""Troco só em dinheiro, quando o restaurante quer assim.

Qualquer forma pode receber acima do restante e devolver troco — a maquininha
cobrou redondo, o cliente pediu parte em espécie. Mas esse troco sai da gaveta
sem dinheiro nenhum ter entrado, e foi um troco de R$ 50 num débito que deixou
a conferência da nuvem R$ 50 acima da loja. O restaurante pode desligar: com
`allow_change_on_non_cash=False`, cartão, PIX e voucher não passam do restante.
"""
from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from apps.core.tenant import tenant_context
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import CashMovement, PaymentMethod
from apps.payments.services import open_cash_register, register_payment

pytestmark = pytest.mark.django_db


@pytest.fixture
def contexto_tenant(account):
    with tenant_context(account):
        yield account


@pytest.fixture
def produto(contexto_tenant, account, restaurant, branch):
    return Product.objects.create(account=account, restaurant=restaurant, branch=branch,
                                  name="Prato", internal_code="TROCO-1", sale_price=Decimal("25.00"))


@pytest.fixture
def venda(contexto_tenant, account, restaurant, branch, manager_user, produto):
    open_cash_register(restaurant=restaurant, user=manager_user, opening_amount=Decimal("100.00"))
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=2, user=manager_user)  # R$ 50
    return pedido


def _forma(account, restaurant, branch, tipo, nome):
    return PaymentMethod.objects.create(account=account, restaurant=restaurant, branch=branch,
                                        name=nome, method_type=tipo)


def _pagar(pedido, user, forma, valor, **extra):
    return register_payment(order=pedido, user=user, payment_method_id=forma.pk,
                            amount=valor, metadata=extra or None)


def test_desligado_o_debito_acima_do_restante_e_recusado(venda, account, restaurant, branch, manager_user):
    restaurant.allow_change_on_non_cash = False
    restaurant.save(update_fields=["allow_change_on_non_cash"])
    debito = _forma(account, restaurant, branch, PaymentMethod.TYPE_CARD, "Cartão de débito")

    with pytest.raises(ValidationError, match="troco só em dinheiro"):
        _pagar(venda, manager_user, debito, "100.00", card_subtype="debit")

    assert not CashMovement.objects.filter(movement_type=CashMovement.TYPE_WITHDRAWAL).exists()


def test_desligado_o_debito_no_valor_exato_passa(venda, account, restaurant, branch, manager_user):
    restaurant.allow_change_on_non_cash = False
    restaurant.save(update_fields=["allow_change_on_non_cash"])
    debito = _forma(account, restaurant, branch, PaymentMethod.TYPE_CARD, "Cartão de débito")

    pagamento = _pagar(venda, manager_user, debito, "50.00", card_subtype="debit")

    assert pagamento.change_amount == Decimal("0.00")


def test_desligado_o_dinheiro_continua_dando_troco(venda, account, restaurant, branch, manager_user):
    restaurant.allow_change_on_non_cash = False
    restaurant.save(update_fields=["allow_change_on_non_cash"])
    dinheiro = _forma(account, restaurant, branch, PaymentMethod.TYPE_CASH, "Dinheiro")

    pagamento = _pagar(venda, manager_user, dinheiro, "100.00")

    assert pagamento.change_amount == Decimal("50.00")


def test_ligado_por_padrao_o_debito_da_troco_como_antes(venda, account, restaurant, branch, manager_user):
    assert restaurant.allow_change_on_non_cash is True
    debito = _forma(account, restaurant, branch, PaymentMethod.TYPE_CARD, "Cartão de débito")

    pagamento = _pagar(venda, manager_user, debito, "100.00", card_subtype="debit")

    assert pagamento.change_amount == Decimal("50.00")
