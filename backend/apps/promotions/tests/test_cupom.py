"""As regras do cupom, cada uma pelo motivo que ela devolve.

O que estes testes protegem não é só o "não": é a FRASE. No caixa, com o cliente
ouvindo, "cupom inválido" faz o operador repetir a digitação três vezes para um
cupom que simplesmente venceu ontem — e a terceira vez o cliente já duvidou da
loja. Por isso cada asserção olha o texto.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.menu.models import Product, ProductCategory
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.promotions.coupon_service import (
    avaliar_no_pedido,
)
from apps.promotions.models import Coupon

CPF = "39053344705"
OUTRO_CPF = "11144477735"


@pytest.fixture
def tenant(account):
    with tenant_context(account):
        yield account


@pytest.fixture
def produto(tenant, account, restaurant, branch):
    categoria = ProductCategory.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Lanches"
    )
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, category=categoria,
        name="X-Burger", internal_code=f"X{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("25.00"),
    )


def _pedido(account, restaurant, branch, user, produto, *, quantidade=2, cpf="", tipo=Order.TYPE_COUNTER):
    pedido = create_order(
        restaurant=restaurant, branch=branch, user=user, order_type=tipo
    )
    add_order_item(order=pedido, product=produto, quantity=quantidade, user=user)
    pedido.refresh_from_db()
    if cpf:
        pedido.fiscal_customer_cpf = cpf
        pedido.save(update_fields=["fiscal_customer_cpf"])
    return pedido


def _cupom(account, **campos):
    campos.setdefault("code", f"C{uuid.uuid4().hex[:6].upper()}")
    campos.setdefault("discount_kind", Coupon.KIND_PERCENT)
    campos.setdefault("discount_value", Decimal("10"))
    return Coupon.objects.create(account=account, **campos)


@pytest.mark.django_db
def test_percentual_abate_sobre_o_subtotal(tenant, account, restaurant, branch, manager_user, produto):
    pedido = _pedido(account, restaurant, branch, manager_user, produto)  # 2 x 25 = 50
    cupom = _cupom(account, discount_value=Decimal("10"))

    motivo, desconto, _ = avaliar_no_pedido(cupom, pedido)
    assert motivo is None
    assert desconto == Decimal("5.00")



@pytest.mark.django_db
def test_o_minimo_nao_conta_taxa_de_servico_nem_entrega(tenant, account, restaurant, branch, manager_user, produto):
    """O pedido chega a 60 com as taxas, mas só tem 50 de produto.

    É o pedido literal: "compra com valor minimo sem contar taxa de serviço e
    entrega". Contar as taxas premiaria uma venda que nunca alcançou o patamar.
    """
    pedido = _pedido(account, restaurant, branch, manager_user, produto)  # 50 em produtos
    pedido.service_fee = Decimal("5.00")
    pedido.delivery_fee = Decimal("5.00")
    pedido.save(update_fields=["service_fee", "delivery_fee"])
    cupom = _cupom(account, minimum_order_value=Decimal("60.00"))

    motivo, desconto, _ = avaliar_no_pedido(cupom, pedido)
    assert "a partir de R$ 60,00 em produtos" in motivo
    assert "sem taxa de serviço e sem entrega" in motivo
    assert desconto == Decimal("0.00")



@pytest.mark.django_db
def test_cupom_vencido_diz_que_venceu(tenant, account, restaurant, branch, manager_user, produto):
    pedido = _pedido(account, restaurant, branch, manager_user, produto)
    ontem = timezone.now() - timedelta(days=1)
    cupom = _cupom(account, starts_at=ontem - timedelta(days=5), ends_at=ontem)

    motivo, _, _ = avaliar_no_pedido(cupom, pedido)
    assert "venceu em" in motivo



@pytest.mark.django_db
def test_cupom_que_exige_cpf_recusa_pedido_sem_cpf(tenant, account, restaurant, branch, manager_user, produto):
    pedido = _pedido(account, restaurant, branch, manager_user, produto)
    cupom = _cupom(account, requires_document=True)

    motivo, _, _ = avaliar_no_pedido(cupom, pedido)
    assert motivo == "Este cupom exige o CPF do cliente na nota."



@pytest.mark.django_db
def test_tipo_de_pedido_restringe(tenant, account, restaurant, branch, manager_user, produto):
    cupom = _cupom(account, order_types=[Order.TYPE_DELIVERY])
    de_balcao = _pedido(account, restaurant, branch, manager_user, produto, tipo=Order.TYPE_COUNTER)

    motivo, _, _ = avaliar_no_pedido(cupom, de_balcao)
    assert motivo == "Este cupom não vale para este tipo de pedido."



@pytest.mark.django_db
def test_entrega_gratis_sem_frete_recusa(tenant, account, restaurant, branch, manager_user, produto):
    cupom = _cupom(account, discount_kind=Coupon.KIND_FREE_DELIVERY, discount_value=Decimal("0"))
    pedido = _pedido(account, restaurant, branch, manager_user, produto)

    motivo, desconto, _ = avaliar_no_pedido(cupom, pedido)
    assert motivo == "Este pedido não tem taxa de entrega para o cupom abater."
    assert desconto == Decimal("0.00")



@pytest.mark.django_db
def test_teto_limita_o_percentual(tenant, account, restaurant, branch, manager_user, produto):
    pedido = _pedido(account, restaurant, branch, manager_user, produto, quantidade=40)  # 1000
    cupom = _cupom(account, discount_value=Decimal("20"), max_discount_amount=Decimal("50.00"))

    _motivo, desconto, _ = avaliar_no_pedido(cupom, pedido)
    assert desconto == Decimal("50.00")


