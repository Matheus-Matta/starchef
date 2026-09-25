"""O cupom pelo caminho que o caixa realmente percorre: o fechamento.

Duas decisões que sozinhas parecem detalhe estão amarradas aqui: o CPF é gravado
ANTES de o cupom ser avaliado (avaliar primeiro recusaria quem acabou de
informá-lo), e o abatimento fica em `coupon_discount`, separado do `discount` do
gerente — somados numa coluna só, o recálculo apagaria o desconto dado à mão.

O que acontece com o cupom DEPOIS de aplicado está em `test_cupom_reavaliado.py`.
"""

import uuid
from decimal import Decimal

import pytest

from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.promotions.models import Coupon

pytestmark = pytest.mark.django_db

CPF = "39053344705"


def _pedido(account, restaurant, branch, user, *, preco=Decimal("30.00"), quantidade=2):
    produto = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Produto cupom", internal_code=f"CUP-{uuid.uuid4().hex[:6]}",
        sale_price=preco,
    )
    pedido = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=user
    )
    add_order_item(order=pedido, product=produto, quantity=quantidade, user=user)
    return pedido


def test_fechar_com_cupom_abate_e_nao_mexe_no_desconto_do_gerente(
    api_client, account, restaurant, branch, manager_user
):
    pedido = _pedido(account, restaurant, branch, manager_user)  # 60,00
    Coupon.objects.create(
        account=account, code="DEZ", discount_kind=Coupon.KIND_PERCENT, discount_value=Decimal("10"),
    )

    resp = api_client.post(
        f"/api/v1/orders/{pedido.id}/close/",
        {"service_fee_enabled": False, "coupon_code": "dez"},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    assert resp.data["coupon_code"] == "DEZ"
    assert Decimal(resp.data["coupon_discount"]) == Decimal("6.00")
    # `discount` continua sendo a decisão de um gerente — e ela é zero aqui.
    assert Decimal(resp.data["discount"]) == Decimal("0.00")
    assert Decimal(resp.data["total"]) == Decimal("54.00")


def test_o_cpf_da_nota_libera_o_cupom_no_mesmo_fechamento(
    api_client, account, restaurant, branch, manager_user
):
    """Um gesto só: o caixa digita CPF e cupom juntos e a venda fecha.

    Se o cupom fosse avaliado antes de o CPF ser gravado, este fechamento
    responderia "exige o CPF do cliente na nota" para um pedido que está
    informando o CPF na mesma requisição.
    """
    pedido = _pedido(account, restaurant, branch, manager_user)
    Coupon.objects.create(
        account=account, code="COMCPF", discount_kind=Coupon.KIND_AMOUNT,
        discount_value=Decimal("5.00"), requires_document=True,
    )

    resp = api_client.post(
        f"/api/v1/orders/{pedido.id}/close/",
        {"service_fee_enabled": False, "fiscal_customer_cpf": CPF, "coupon_code": "COMCPF"},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    assert Decimal(resp.data["coupon_discount"]) == Decimal("5.00")


def test_cupom_recusado_devolve_422_com_o_motivo_e_nao_fecha(
    api_client, account, restaurant, branch, manager_user
):
    pedido = _pedido(account, restaurant, branch, manager_user)  # 60,00
    Coupon.objects.create(
        account=account, code="CEM", discount_kind=Coupon.KIND_PERCENT,
        discount_value=Decimal("10"), minimum_order_value=Decimal("100.00"),
    )

    resp = api_client.post(
        f"/api/v1/orders/{pedido.id}/close/",
        {"service_fee_enabled": False, "coupon_code": "CEM"},
        format="json",
    )

    assert resp.status_code == 422, resp.data
    corpo = resp.json()["error"]
    assert corpo["code"] == "coupon_rejected"
    assert "a partir de R$ 100,00 em produtos" in str(corpo["message"])
    # O fechamento é atômico: o pedido continua aberto, sem estado pela metade.
    pedido.refresh_from_db()
    assert pedido.status == Order.STATUS_OPEN
    assert pedido.coupon_id is None
