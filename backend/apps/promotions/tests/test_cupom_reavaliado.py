"""O cupom depois de aplicado: ele muda, sai, volta, e só queima no pagamento.

Um cupom não é um valor gravado — é uma regra que continua sendo verdadeira ou
deixa de ser. Quem aplica um cupom de "acima de R$ 50" num pedido de R$ 60 e
remove metade dos itens não pode continuar com o desconto, e ninguém revisa um
total que já apareceu certo na tela uma vez.
"""

import uuid
from decimal import Decimal

import pytest

from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.promotions.models import Coupon, CouponRedemption

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


def test_codigo_vazio_retira_o_cupom_que_estava_aplicado(
    api_client, account, restaurant, branch, manager_user
):
    """Vazio significa "sem cupom", e não "não mexe".

    O caixa pode ter apagado o código de propósito, porque o cliente desistiu
    dele — e nesse caso o desconto tem de sair.
    """
    pedido = _pedido(account, restaurant, branch, manager_user)
    Coupon.objects.create(
        account=account, code="SAI", discount_kind=Coupon.KIND_AMOUNT, discount_value=Decimal("5.00"),
    )
    api_client.post(
        f"/api/v1/orders/{pedido.id}/close/",
        {"service_fee_enabled": False, "coupon_code": "SAI"},
        format="json",
    )

    resp = api_client.post(
        f"/api/v1/orders/{pedido.id}/close/",
        {"service_fee_enabled": False, "coupon_code": ""},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    assert resp.data["coupon_code"] == ""
    assert Decimal(resp.data["coupon_discount"]) == Decimal("0.00")
    assert Decimal(resp.data["total"]) == Decimal("60.00")



def test_reabrir_o_fechamento_sem_informar_cupom_preserva_o_que_havia(
    api_client, account, restaurant, branch, manager_user
):
    """Fechar de novo para corrigir a taxa não pode derrubar o cupom."""
    pedido = _pedido(account, restaurant, branch, manager_user)
    Coupon.objects.create(
        account=account, code="FICA", discount_kind=Coupon.KIND_AMOUNT, discount_value=Decimal("5.00"),
    )
    api_client.post(
        f"/api/v1/orders/{pedido.id}/close/",
        {"service_fee_enabled": False, "coupon_code": "FICA"},
        format="json",
    )

    resp = api_client.post(
        f"/api/v1/orders/{pedido.id}/close/", {"service_fee_enabled": True}, format="json"
    )

    assert resp.status_code == 200, resp.data
    assert resp.data["coupon_code"] == "FICA"
    assert Decimal(resp.data["coupon_discount"]) == Decimal("5.00")



def test_remover_itens_derruba_o_cupom_que_deixou_de_se_qualificar(
    api_client, account, restaurant, branch, manager_user
):
    """O cupom é REAVALIADO a cada recálculo, e não congelado na aplicação.

    Quem aplica um cupom de "acima de R$ 50" num pedido de R$ 60 e depois
    remove metade dos itens não pode continuar com o desconto — e ninguém revisa
    um total que já apareceu certo na tela uma vez.
    """
    from apps.core.tenant import tenant_context
    from apps.orders.services import recalculate_order

    pedido = _pedido(account, restaurant, branch, manager_user)  # 2 x 30 = 60
    Coupon.objects.create(
        account=account, code="ACIMA50", discount_kind=Coupon.KIND_AMOUNT,
        discount_value=Decimal("5.00"), minimum_order_value=Decimal("50.00"),
    )
    api_client.post(
        f"/api/v1/orders/{pedido.id}/close/",
        {"service_fee_enabled": False, "coupon_code": "ACIMA50"},
        format="json",
    )
    pedido.refresh_from_db()
    assert pedido.coupon_discount == Decimal("5.00")

    # Cai para 30,00: abaixo do mínimo do cupom.
    with tenant_context(account):
        item = pedido.items.first()
        item.quantity = 1
        item.total_price = Decimal("30.00")
        item.save(update_fields=["quantity", "total_price"])
        recalculate_order(pedido)

    pedido.refresh_from_db()
    assert pedido.coupon_discount == Decimal("0.00")
    assert pedido.total == Decimal("30.00")
    # O VÍNCULO fica: o pedido pode voltar a se qualificar no item seguinte, e
    # reaplicar sozinho é melhor do que obrigar o caixa a digitar de novo.
    assert pedido.coupon_code == "ACIMA50"



def test_o_resgate_nasce_no_pagamento_e_nao_no_fechamento(
    api_client, account, restaurant, branch, manager_user
):
    pedido = _pedido(account, restaurant, branch, manager_user)
    cupom = Coupon.objects.create(
        account=account, code="UMAVEZ", discount_kind=Coupon.KIND_AMOUNT,
        discount_value=Decimal("5.00"), single_use_per_customer=True,
    )
    api_client.post(
        f"/api/v1/orders/{pedido.id}/close/",
        {"service_fee_enabled": False, "fiscal_customer_cpf": CPF, "coupon_code": "UMAVEZ"},
        format="json",
    )

    # Fechado, mas não pago: o direito do cliente continua intacto.
    assert CouponRedemption.all_objects.filter(coupon=cupom).count() == 0

    from apps.promotions.coupon_service import registrar_resgate

    pedido.refresh_from_db()
    registrar_resgate(pedido)
    resgate = CouponRedemption.all_objects.get(coupon=cupom)
    # O CPF fica GRAVADO no resgate: quem volta com outro cadastro e o mesmo CPF
    # continua sendo a mesma pessoa.
    assert resgate.document == CPF
    assert resgate.amount == Decimal("5.00")
