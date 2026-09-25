"""Mexer no cupom durante o PAGAMENTO — aplicar, trocar e retirar.

O cliente lembra do cupom no meio do pagamento. É o caso normal, não a exceção:
ele tira o celular do bolso quando o caixa fala o total. Obrigá-lo a esperar o
caixa desfazer o fechamento por causa disso é o que a rota evita.

O que estes testes protegem é o limite: o total nunca pode cair abaixo do
dinheiro que já entrou na gaveta, e venda paga não muda mais.
"""

import uuid
from decimal import Decimal

import pytest

from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import Payment, PaymentMethod

pytestmark = pytest.mark.django_db

ROTA = "/api/v1/orders"


@pytest.fixture
def cupom(account):
    from apps.promotions.models import Coupon

    return Coupon.objects.create(
        account=account, code="DEZREAIS", discount_kind=Coupon.KIND_AMOUNT,
        discount_value=Decimal("10.00"),
    )


def _pedido_fechado(api_client, account, restaurant, branch, user, *, total_alvo="60.00"):
    produto = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Produto pagamento", internal_code=f"PG-{uuid.uuid4().hex[:6]}",
        sale_price=Decimal(total_alvo),
    )
    pedido = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=user
    )
    add_order_item(order=pedido, product=produto, quantity=1, user=user)
    resp = api_client.post(f"{ROTA}/{pedido.id}/close/", {"service_fee_enabled": False}, format="json")
    assert resp.status_code == 200, resp.data
    pedido.refresh_from_db()
    return pedido


def test_aplicar_cupom_na_tela_de_pagamento_refaz_o_total(
    api_client, account, restaurant, branch, manager_user, cupom
):
    """O total volta JÁ refeito: o teclado do caixa desenha o troco a partir dele."""
    pedido = _pedido_fechado(api_client, account, restaurant, branch, manager_user)

    resp = api_client.post(f"{ROTA}/{pedido.id}/apply-coupon/", {"code": "dezreais"}, format="json")

    assert resp.status_code == 200, resp.data
    assert resp.data["coupon_code"] == "DEZREAIS"
    assert Decimal(resp.data["coupon_discount"]) == Decimal("10.00")
    assert Decimal(resp.data["total"]) == Decimal("50.00")
    # A conta continua em pagamento: mexer no cupom não reabre nem fecha nada.
    assert resp.data["status"] == Order.STATUS_AWAITING_PAYMENT


def test_retirar_o_cupom_na_tela_de_pagamento_devolve_o_total_cheio(
    api_client, account, restaurant, branch, manager_user, cupom
):
    pedido = _pedido_fechado(api_client, account, restaurant, branch, manager_user)
    api_client.post(f"{ROTA}/{pedido.id}/apply-coupon/", {"code": "DEZREAIS"}, format="json")

    resp = api_client.post(f"{ROTA}/{pedido.id}/apply-coupon/", {"code": ""}, format="json")

    assert resp.status_code == 200, resp.data
    assert resp.data["coupon_code"] == ""
    assert Decimal(resp.data["total"]) == Decimal("60.00")


def test_trocar_o_cupom_substitui_sem_somar(
    api_client, account, restaurant, branch, manager_user, cupom
):
    """Dois cupons não se empilham: o segundo ocupa o lugar do primeiro."""
    from apps.promotions.models import Coupon

    Coupon.objects.create(
        account=account, code="VINTE", discount_kind=Coupon.KIND_AMOUNT,
        discount_value=Decimal("20.00"),
    )
    pedido = _pedido_fechado(api_client, account, restaurant, branch, manager_user)
    api_client.post(f"{ROTA}/{pedido.id}/apply-coupon/", {"code": "DEZREAIS"}, format="json")

    resp = api_client.post(f"{ROTA}/{pedido.id}/apply-coupon/", {"code": "VINTE"}, format="json")

    assert resp.status_code == 200, resp.data
    assert resp.data["coupon_code"] == "VINTE"
    assert Decimal(resp.data["coupon_discount"]) == Decimal("20.00")
    assert Decimal(resp.data["total"]) == Decimal("40.00")


def test_cupom_recusado_no_pagamento_nao_muda_o_total(
    api_client, account, restaurant, branch, manager_user
):
    from apps.promotions.models import Coupon

    Coupon.objects.create(
        account=account, code="ALTO", discount_kind=Coupon.KIND_AMOUNT,
        discount_value=Decimal("5.00"), minimum_order_value=Decimal("500.00"),
    )
    pedido = _pedido_fechado(api_client, account, restaurant, branch, manager_user)

    resp = api_client.post(f"{ROTA}/{pedido.id}/apply-coupon/", {"code": "ALTO"}, format="json")

    assert resp.status_code == 422, resp.data
    assert resp.json()["error"]["code"] == "coupon_rejected"
    pedido.refresh_from_db()
    assert pedido.coupon_id is None
    assert pedido.total == Decimal("60.00")


def test_o_cupom_nao_pode_derrubar_o_total_abaixo_do_ja_recebido(
    api_client, account, restaurant, branch, manager_user, cupom
):
    """A guarda que protege a gaveta.

    O cliente pagou os R$ 60 em dinheiro e só então lembrou do cupom de R$ 10.
    Aplicar deixaria o caixa devendo R$ 10 que nenhum troco registrou — e essa
    decisão é de uma pessoa, estornando o recebimento antes.
    """
    pedido = _pedido_fechado(api_client, account, restaurant, branch, manager_user)
    metodo = PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Dinheiro", method_type=PaymentMethod.TYPE_CASH,
    )
    # O recebimento entra DIRETO, e não pela rota: cobrar exige sessão de caixa
    # aberta, e o que está sob teste é a guarda do cupom — não a abertura do
    # caixa. A guarda lê pagamento APROVADO, que é exatamente o que criamos.
    Payment.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        order=pedido, payment_method=metodo, amount=Decimal("60.00"),
        status=Payment.STATUS_APPROVED,
    )

    resp = api_client.post(f"{ROTA}/{pedido.id}/apply-coupon/", {"code": "DEZREAIS"}, format="json")

    assert resp.status_code == 422, resp.data
    assert "já recebido" in str(resp.json()["error"]["message"])
    # A TRANSAÇÃO DESFEZ a aplicação: o pedido não pode ficar com o desconto
    # que acabou de ser recusado.
    pedido.refresh_from_db()
    assert pedido.coupon_id is None
    assert pedido.coupon_discount == Decimal("0.00")
    assert pedido.total == Decimal("60.00")


def test_sem_a_chave_code_a_rota_recusa_com_400(
    api_client, account, restaurant, branch, manager_user
):
    """Não existe "não mexe" numa rota cujo único propósito é mexer."""
    pedido = _pedido_fechado(api_client, account, restaurant, branch, manager_user)

    resp = api_client.post(f"{ROTA}/{pedido.id}/apply-coupon/", {}, format="json")

    assert resp.status_code == 400, resp.data
