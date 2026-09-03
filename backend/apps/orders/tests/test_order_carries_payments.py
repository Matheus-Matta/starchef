"""O pedido carrega os recebimentos que ja subiram.

`payments` e uma relacao reversa: `fields = "__all__"` nao a incluia. O PDV
grava o recebimento local-first e, quando a fila entrega, aplica por cima a
versao do servidor — que vinha SEM pagamento nenhum. O pedido ficava sem
recebimento no armazenamento local no instante seguinte a sincronizacao, e era
desse retrato que a emissao fiscal era montada: o terminal recusava a propria
venda com "A venda nao tem recebimento registrado" e a NFC-e nunca saia.
"""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.serializers import OrderSerializer
from apps.orders.services import add_order_item, create_order
from apps.payments.models import PaymentMethod
from apps.payments.services import cancel_payment, register_payment

pytestmark = pytest.mark.django_db


@pytest.fixture
def paid_order(account, restaurant, branch, manager_user):
    product = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Refrigerante", internal_code=f"P{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("7.00"),
    )
    method = PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Dinheiro", method_type=PaymentMethod.TYPE_CASH,
    )
    # O caixa aberto nao e o assunto deste teste.
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    order = create_order(
        restaurant=restaurant, branch=branch,
        order_type=Order.TYPE_COUNTER, user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    order.refresh_from_db()
    register_payment(
        order=order, user=manager_user,
        payment_method_id=method.id, amount=order.total,
    )
    order.refresh_from_db()
    return order, method


def test_pedido_serializado_traz_os_recebimentos(paid_order, account):
    order, method = paid_order

    with tenant_context(account):
        data = OrderSerializer(order).data

    assert "payments" in data
    assert len(data["payments"]) == 1
    payment = data["payments"][0]
    assert Decimal(payment["amount"]) == order.total
    # O nome da forma de pagamento vai junto: e o que a NFC-e imprime e o que a
    # tela mostra num pedido pago reaberto.
    assert payment["payment_method_name"] == method.name


def test_recebimento_cancelado_nao_compoe_o_pedido(paid_order, account, manager_user):
    order, _ = paid_order

    with tenant_context(account):
        payment = order.payments.first()
        cancel_payment(payment=payment, user=manager_user)
        order.refresh_from_db()

        # Um recebimento cancelado nao entra no valor pago nem na nota.
        assert OrderSerializer(order).data["payments"] == []
