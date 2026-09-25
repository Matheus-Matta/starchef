"""O cupom contra a PESSOA: CPF, grupo, limite e resgate.

A identidade aqui é o CPF da nota — o mesmo que o cliente informa no pedido.
Não existe "cliente selecionado" à parte: no caixa, o que a pessoa diz é o CPF,
e uma segunda fonte de identidade faria "compra única por cliente" perder o
sentido no primeiro cadastro duplicado.

O resgate é a prova do uso, e ele só nasce no PAGAMENTO. É a diferença entre
reservar um direito e consumi-lo.
"""

import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.customers.models import Customer, CustomerGroup
from apps.menu.models import Product, ProductCategory
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.promotions.coupon_service import (
    aplicar_cupom,
    avaliar_no_pedido,
    devolver_resgate,
    registrar_resgate,
)
from apps.promotions.models import Coupon, CouponRedemption

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
def test_compra_unica_por_cliente_barra_o_mesmo_cpf(tenant, account, restaurant, branch, manager_user, produto):
    """O segundo pedido do MESMO CPF é recusado — e o primeiro não é afetado."""
    cupom = _cupom(account, single_use_per_customer=True)
    primeiro = _pedido(account, restaurant, branch, manager_user, produto, cpf=CPF)
    aplicar_cupom(primeiro, cupom.code)
    primeiro.status = Order.STATUS_PAID
    primeiro.save(update_fields=["status"])
    registrar_resgate(primeiro)

    segundo = _pedido(account, restaurant, branch, manager_user, produto, cpf=CPF)
    motivo, _, _ = avaliar_no_pedido(cupom, segundo)
    assert motivo == "Este CPF já usou este cupom — ele vale uma vez por cliente."

    # Outro CPF continua tendo direito: o limite é por pessoa, não global.
    de_outro = _pedido(account, restaurant, branch, manager_user, produto, cpf=OUTRO_CPF)
    assert avaliar_no_pedido(cupom, de_outro)[0] is None



@pytest.mark.django_db
def test_o_resgate_so_nasce_no_pagamento(tenant, account, restaurant, branch, manager_user, produto):
    """Aplicar não queima o cupom. Só o pagamento queima.

    Gravado na aplicação, um cupom de compra única morreria num pedido que o
    cliente desistiu de fechar — e o direito dele iria embora sem compra.
    """
    cupom = _cupom(account, single_use_per_customer=True)
    pedido = _pedido(account, restaurant, branch, manager_user, produto, cpf=CPF)
    aplicar_cupom(pedido, cupom.code)

    assert CouponRedemption.all_objects.filter(coupon=cupom).count() == 0
    registrar_resgate(pedido)
    assert CouponRedemption.all_objects.filter(coupon=cupom).count() == 1
    # Idempotente: pagamento reconfirmado (fila offline, webhook repetido) não
    # gera um segundo resgate.
    registrar_resgate(pedido)
    assert CouponRedemption.all_objects.filter(coupon=cupom).count() == 1



@pytest.mark.django_db
def test_cancelar_o_pedido_devolve_o_direito(tenant, account, restaurant, branch, manager_user, produto):
    cupom = _cupom(account, single_use_per_customer=True)
    pedido = _pedido(account, restaurant, branch, manager_user, produto, cpf=CPF)
    aplicar_cupom(pedido, cupom.code)
    registrar_resgate(pedido)

    devolver_resgate(pedido)
    novo = _pedido(account, restaurant, branch, manager_user, produto, cpf=CPF)
    assert avaliar_no_pedido(cupom, novo)[0] is None



@pytest.mark.django_db
def test_cupom_de_grupo_confere_o_grupo_pelo_cpf(tenant, account, restaurant, branch, manager_user, produto):
    """A elegibilidade sai do CPF da nota — não de um cliente escolhido à parte."""
    grupo = CustomerGroup.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="VIP"
    )
    cliente = Customer.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Maria", phone="11999990000", document=CPF,
    )
    cliente.groups.add(grupo)
    cupom = _cupom(account)
    cupom.customer_groups.add(grupo)

    do_vip = _pedido(account, restaurant, branch, manager_user, produto, cpf=CPF)
    assert avaliar_no_pedido(cupom, do_vip)[0] is None

    # Um CPF que não está em grupo nenhum é recusado, e a frase diz por quê.
    de_fora = _pedido(account, restaurant, branch, manager_user, produto, cpf=OUTRO_CPF)
    motivo, _, _ = avaliar_no_pedido(cupom, de_fora)
    assert motivo == "Este CPF não está na lista de clientes deste cupom."



@pytest.mark.django_db
def test_cupom_restrito_sem_cpf_pede_o_cpf(tenant, account, restaurant, branch, manager_user, produto):
    """Restrito a grupo, mas `requires_document` desmarcado: o CPF é exigido igual.

    Sem CPF não existe a quem comparar. Deixar passar liberaria o cupom de VIP
    para qualquer um que soubesse o código.
    """
    grupo = CustomerGroup.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Corporativo"
    )
    cupom = _cupom(account, requires_document=False)
    cupom.customer_groups.add(grupo)

    pedido = _pedido(account, restaurant, branch, manager_user, produto)
    motivo, _, _ = avaliar_no_pedido(cupom, pedido)
    assert "informe o CPF" in motivo



@pytest.mark.django_db
def test_limite_total_esgota(tenant, account, restaurant, branch, manager_user, produto):
    cupom = _cupom(account, usage_limit=1)
    primeiro = _pedido(account, restaurant, branch, manager_user, produto, cpf=CPF)
    aplicar_cupom(primeiro, cupom.code)
    registrar_resgate(primeiro)

    segundo = _pedido(account, restaurant, branch, manager_user, produto, cpf=OUTRO_CPF)
    motivo, _, _ = avaliar_no_pedido(cupom, segundo)
    assert motivo == "Este cupom já atingiu o limite de usos."
