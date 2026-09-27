"""O resgate do cupom pelo caminho que o CAIXA percorre: fecha, depois cobra.

Este arquivo existe por causa de um defeito que o teste de carga achou e a
unidade não: eu havia ligado o resgate em `orders.services.close_order`, no ramo
"pago integralmente" — que só dispara quando alguém fecha DE NOVO um pedido já
pago. O caixa não faz isso. Ele fecha a conta e então cobra, e a cobrança passa
por `payments.services`, que não gravava resgate nenhum.

O tamanho do estrago: ZERO resgates para seis vendas pagas com o mesmo cupom de
uso único. Sem resgate, `usos_do_cupom` responde zero para sempre — e
"compra única por cliente", "usos por cliente" e "limite total" não valiam
absolutamente nada. O cupom era infinito.

São DOIS caminhos para um pedido virar pago, e o código de produção já carregava
um comentário avisando exatamente isso sobre as anotações da comanda. Caí na
mesma armadilha que o comentário descrevia.
"""

import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product, ProductCategory
from apps.orders.models import Order
from apps.payments.models import PaymentMethod
from apps.promotions.models import Coupon, CouponRedemption

pytestmark = pytest.mark.django_db

ROTA = "/api/v1/orders"
CPF = "39053344705"


# As fixtures são locais porque `conftest` do pytest é por DIRETÓRIO: as de
# `apps/orders/tests/` não alcançam aqui. Importá-las de lá amarraria os dois
# pacotes de teste e quebraria no dia em que uma delas mudasse de nome.
@pytest.fixture
def cenario(account, restaurant):
    """Restaurante sem exigência de caixa aberto — não é o assunto daqui."""
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    with tenant_context(account):
        yield restaurant


@pytest.fixture
def produto(cenario, account, restaurant, branch):
    categoria = ProductCategory.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Lanches"
    )
    produto = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, category=categoria,
        name="X-Burger", internal_code=f"X{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("25.00"),
    )
    produto.restaurants.add(restaurant)
    return produto


@pytest.fixture
def dinheiro(account, restaurant, branch):
    return PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Dinheiro", method_type=PaymentMethod.TYPE_CASH,
    )


def pagar(api, pedido, metodo, valor):
    return api.post(f"{ROTA}/{pedido}/pay/",
                    {"payment_method": str(metodo.pk), "amount": str(valor)},
                    format="json")


@pytest.fixture
def cupom(account, cenario):
    return Coupon.objects.create(
        account=account, code="UNICO", discount_kind=Coupon.KIND_AMOUNT,
        discount_value=Decimal("5.00"), single_use_per_customer=True,
    )


def _vender(api_client, restaurant, produto, *, codigo="", cpf=""):
    """Abre com item, fecha (com o cupom) e devolve o pedido fechado."""
    criado = api_client.post(
        f"{ROTA}/create-with-item/",
        {"order_type": Order.TYPE_COUNTER, "restaurant": str(restaurant.pk),
         "item": {"product": str(produto.pk), "quantity": 2}},
        format="json",
    )
    assert criado.status_code in (200, 201), criado.data
    pedido = criado.data["id"]
    fechado = api_client.post(
        f"{ROTA}/{pedido}/close/",
        {"service_fee_enabled": False, "fiscal_customer_cpf": cpf,
         "coupon_code": codigo},
        format="json",
    )
    return pedido, fechado


def test_pagar_pela_rota_do_caixa_GRAVA_o_resgate(
    api_client, cenario, produto, cupom, dinheiro
):
    """A regressão. Fechar e cobrar tem de deixar o resgate gravado."""
    pedido, fechado = _vender(api_client, cenario, produto, codigo="UNICO", cpf=CPF)
    assert fechado.status_code == 200, fechado.data
    assert Decimal(fechado.data["coupon_discount"]) == Decimal("5.00")
    # Ainda não pagou: o direito do cliente continua intacto.
    assert CouponRedemption.all_objects.filter(coupon=cupom).count() == 0

    recebido = pagar(api_client, pedido, dinheiro, fechado.data["total"])

    assert recebido.status_code == 201, recebido.data
    resgates = CouponRedemption.all_objects.filter(coupon=cupom)
    assert resgates.count() == 1, "o resgate não nasceu no caminho do caixa"
    assert resgates.first().document == CPF


def test_o_segundo_uso_do_MESMO_CPF_e_recusado_no_pagamento(
    api_client, cenario, produto, cupom, dinheiro
):
    """Com o resgate gravado, o limite passa a valer de verdade.

    A recusa vem no PAGAMENTO, e não no fechamento, quando a segunda venda foi
    fechada antes de a primeira ser paga — é a janela que a corrida explora.
    """
    primeiro, fechado1 = _vender(api_client, cenario, produto, codigo="UNICO", cpf=CPF)
    segundo, fechado2 = _vender(api_client, cenario, produto, codigo="UNICO", cpf=CPF)
    # As duas passaram no fechamento: nenhuma foi paga ainda, e nesse instante
    # as duas TÊM direito. É exatamente aqui que o defeito morava.
    assert fechado1.status_code == 200, fechado1.data
    assert fechado2.status_code == 200, fechado2.data

    pago1 = pagar(api_client, primeiro, dinheiro, fechado1.data["total"])
    assert pago1.status_code == 201, pago1.data

    pago2 = pagar(api_client, segundo, dinheiro, fechado2.data["total"])

    assert pago2.status_code == 422, pago2.data
    assert pago2.json()["error"]["code"] == "coupon_rejected"
    assert "já foi usado por este cliente" in str(pago2.json()["error"]["message"])
    # A TRANSAÇÃO DESFEZ O RECEBIMENTO: recusar depois de gravar o pagamento
    # deixaria dinheiro no caixa de uma venda que não fechou.
    segundo_pedido = Order.all_objects.get(pk=segundo)
    assert segundo_pedido.payment_status != Order.PAYMENT_PAID
    assert CouponRedemption.all_objects.filter(coupon=cupom).count() == 1


def test_o_teto_total_passa_a_valer(api_client, account, cenario, produto, dinheiro):
    """Teto de um uso, duas vendas fechadas: a segunda não paga."""
    Coupon.objects.create(
        account=account, code="TETO1", discount_kind=Coupon.KIND_AMOUNT,
        discount_value=Decimal("3.00"), usage_limit=1,
    )
    primeiro, f1 = _vender(api_client, cenario, produto, codigo="TETO1")
    segundo, f2 = _vender(api_client, cenario, produto, codigo="TETO1")

    assert pagar(api_client, primeiro, dinheiro, f1.data["total"]).status_code == 201
    recusado = pagar(api_client, segundo, dinheiro, f2.data["total"])

    assert recusado.status_code == 422, recusado.data
    assert "esgotou o limite de usos" in str(recusado.json()["error"]["message"])


def test_pagar_duas_vezes_nao_duplica_o_resgate(
    api_client, cenario, produto, cupom, dinheiro
):
    """A fila offline reenvia, e o webhook repete. O resgate é um só."""
    pedido, fechado = _vender(api_client, cenario, produto, codigo="UNICO", cpf=CPF)
    total = fechado.data["total"]
    assert pagar(api_client, pedido, dinheiro, total).status_code == 201
    # Segundo recebimento no mesmo pedido já pago: o backend recusa ou ignora, e
    # em nenhum dos casos pode nascer um segundo resgate.
    pagar(api_client, pedido, dinheiro, total)

    assert CouponRedemption.all_objects.filter(coupon=cupom).count() == 1
