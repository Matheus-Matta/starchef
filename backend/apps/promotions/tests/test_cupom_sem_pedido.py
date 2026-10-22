"""Conferir o cupom da venda que AINDA NÃO EXISTE no servidor.

A venda nova é montada no PDV. Para aplicar um cupom, o PDV pedia ao servidor
a simulação da venda inteira — criar o pedido, lançar cada item, fechar e
desfazer, 60 a 120 consultas — só para saber o desconto. Agora ele manda os
números (subtotal, frete, tipo, CPF, produtos) e recebe as MESMAS regras
(`coupon_rules.avaliar`) aplicadas a eles. A conclusão confere de novo.
"""
import uuid
from decimal import Decimal

import pytest

from apps.menu.models import Product
from apps.promotions.models import Coupon, DiscountTable, Promotion, PromotionProduct

pytestmark = pytest.mark.django_db
URL = "/api/v1/promotions/coupons/validate/"


def _cupom(account, **campos):
    campos.setdefault("code", f"C{uuid.uuid4().hex[:6].upper()}")
    campos.setdefault("discount_kind", Coupon.KIND_PERCENT)
    campos.setdefault("discount_value", Decimal("10"))
    return Coupon.objects.create(account=account, **campos)


def _conferir(api_client, codigo, **venda):
    corpo = {"code": codigo, "subtotal": "200.00", "order_type": "counter", **venda}
    resposta = api_client.post(URL, corpo, format="json")
    assert resposta.status_code == 200, resposta.data
    return resposta.data


def test_percentual_com_teto_sem_pedido(api_client, account):
    cupom = _cupom(account, discount_value=Decimal("10"), max_discount_amount=Decimal("15.00"))

    dados = _conferir(api_client, cupom.code.lower())

    assert dados["valid"] is True
    assert Decimal(str(dados["discount"])) == Decimal("15.00")
    assert dados["coupon"]["code"] == cupom.code


def test_minimo_sobre_produtos_recusa_com_o_motivo(api_client, account):
    cupom = _cupom(account, minimum_order_value=Decimal("300.00"))

    dados = _conferir(api_client, cupom.code)

    assert dados["valid"] is False
    assert "a partir de R$ 300,00 em produtos" in dados["reason"]


def test_cupom_limitado_por_cliente_pede_o_cpf(api_client, account):
    cupom = _cupom(account, first_purchase_only=True)

    sem_cpf = _conferir(api_client, cupom.code)
    com_cpf = _conferir(api_client, cupom.code, cpf="529.982.247-25")

    assert sem_cpf["valid"] is False and "CPF" in sem_cpf["reason"]
    assert com_cpf["valid"] is True


def test_cupom_que_nao_acumula_olha_os_produtos_da_venda(api_client, account, restaurant, branch):
    cupom = _cupom(account, combines_with_promotions=False)
    produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch, name="Suco",
                                     internal_code=f"S{uuid.uuid4().hex[:6]}", sale_price=Decimal("10.00"))
    regra = Promotion.objects.create(account=account, table=DiscountTable.objects.create(account=account, name="Encarte"),
                                     name="Suco", target_type="products", discount_kind="fixed")
    PromotionProduct.objects.create(account=account, promotion=regra, product=produto,
                                    promotional_price=Decimal("8.00"), compare_at_price=Decimal("10.00"))

    dados = _conferir(api_client, cupom.code, products=[str(produto.pk)], restaurant=str(restaurant.pk))

    assert dados["valid"] is False
    assert "não acumula com promoção" in dados["reason"]


def test_sem_pedido_e_sem_subtotal_e_400(api_client, account):
    cupom = _cupom(account)

    resposta = api_client.post(URL, {"code": cupom.code}, format="json")

    assert resposta.status_code == 400
