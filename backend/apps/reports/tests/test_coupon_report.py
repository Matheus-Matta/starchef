"""Relatório por cupom: usos, quanto foi descontado e quanto a venda rendeu.

Só pedido PAGO entra. O pedido cancelado devolve o resgate (o cupom volta a
valer), e contá-lo mostraria desconto de uma venda que não existiu.
"""
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.orders.models import Order
from apps.promotions.models import Coupon, CouponRedemption

pytestmark = pytest.mark.django_db

ROTA = "/api/v1/reports/coupons/"


@pytest.fixture
def cupons(account, restaurant):
    with tenant_context(account):
        dez = Coupon.objects.create(account=account, code="DEZ", name="Dez por cento")
        frete = Coupon.objects.create(account=account, code="FRETE", name="Frete grátis")

        def venda(cupom, numero, total, desconto, *, status=Order.STATUS_PAID, documento=""):
            pago = status == Order.STATUS_PAID
            pedido = Order.objects.create(
                account=account, restaurant=restaurant, sequence=numero, status=status,
                payment_status=Order.PAYMENT_PAID if pago else Order.PAYMENT_CANCELLED,
                total=Decimal(total), coupon_discount=Decimal(desconto),
            )
            CouponRedemption.objects.create(
                account=account, restaurant=restaurant, coupon=cupom, order=pedido,
                amount=Decimal(desconto), document=documento,
            )

        venda(dez, 1, "90.00", "10.00", documento="12345678901")
        venda(dez, 2, "45.05", "5.01")
        venda(frete, 3, "30.00", "8.00")
        # Cancelado: não pode somar nada.
        venda(dez, 4, "100.00", "11.11", status=Order.STATUS_CANCELLED)
    return {"dez": dez, "frete": frete}


def test_por_cupom_soma_usos_desconto_liquido_e_bruto(cupons, admin_client):
    resposta = admin_client.get(ROTA)

    assert resposta.status_code == 200, resposta.data
    linhas = {linha["code"]: linha for linha in resposta.data["by_coupon"]}
    assert linhas["DEZ"]["uses"] == 2
    assert Decimal(linhas["DEZ"]["discount"]) == Decimal("15.01")
    assert Decimal(linhas["DEZ"]["net"]) == Decimal("135.05")
    assert Decimal(linhas["DEZ"]["gross"]) == Decimal("150.06")
    assert linhas["FRETE"]["uses"] == 1
    totais = resposta.data["totals"]
    assert totais["uses"] == 3
    assert Decimal(totais["discount"]) == Decimal("23.01")


def test_o_detalhe_do_cupom_lista_cada_uso_com_cpf_mascarado(cupons, admin_client):
    resposta = admin_client.get(ROTA, {"coupon": str(cupons["dez"].pk)})

    assert resposta.status_code == 200, resposta.data
    usos = resposta.data["redemptions"]
    assert [u["order_sequence"] for u in usos] == [2, 1]
    com_cpf = next(u for u in usos if u["order_sequence"] == 1)
    assert com_cpf["document"] == "***.456.789-**"
    assert Decimal(com_cpf["discount"]) == Decimal("10.00")


def test_exporta_csv(cupons, admin_client):
    resposta = admin_client.get(ROTA, {"export": "csv"})

    assert resposta.status_code == 200
    conteudo = resposta.content.decode("utf-8")
    assert "DEZ" in conteudo and "15.01" in conteudo


def test_periodo_invalido_e_400(admin_client):
    assert admin_client.get(ROTA, {"date_from": "ontem"}).status_code == 400
