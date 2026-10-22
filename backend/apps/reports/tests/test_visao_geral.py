"""A Visão Geral: o dia por padrão, um pouco de cada relatório, sem zeros.

O dashboard antigo misturava hoje, sete dias e o mês na mesma tela, e não
mostrava formas de pagamento, comandas pagas nem o dinheiro em cada caixa.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import CashMovement, CashRegister, CashStation, PaymentMethod
from apps.payments.services import register_payment

pytestmark = pytest.mark.django_db
URL = "/api/v1/reports/overview/"


@pytest.fixture
def loja(account, restaurant, branch, manager_user):
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    estacao = CashStation.objects.create(account=account, restaurant=restaurant,
                                         name="Caixa 1", code="C1")
    sessao = CashRegister.objects.create(
        account=account, restaurant=restaurant, branch=branch, opened_by=manager_user,
        cash_station=estacao, opening_amount="100.00", created_by=manager_user, updated_by=manager_user)
    CashMovement.objects.create(account=account, restaurant=restaurant, branch=branch,
                                cash_register=sessao, operator=manager_user,
                                movement_type=CashMovement.TYPE_OPENING, amount=Decimal("100.00"))
    produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch, name="Prato",
                                     internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("40.00"))

    def forma(tipo):
        return PaymentMethod.objects.create(account=account, restaurant=restaurant, branch=branch,
                                            name=f"{tipo} da loja", method_type=tipo)

    dinheiro, pix = forma("cash"), forma("pix")

    def vender(metodo, quando=None):
        pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                              user=manager_user)
        add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
        pedido.refresh_from_db()
        register_payment(order=pedido, user=manager_user, payment_method_id=metodo.pk,
                         amount="40.00", cash_register_id=sessao.pk)
        if quando:
            Order.all_objects.filter(pk=pedido.pk).update(opened_at=quando)
        return pedido

    vender(dinheiro)
    vender(pix)
    return vender, dinheiro


def test_o_dia_e_o_padrao_e_traz_um_pouco_de_cada(api_client, restaurant, loja):
    dados = api_client.get(URL, {"restaurant": str(restaurant.pk)}).json()

    assert dados["periodo"]["nome"] == "dia"
    assert Decimal(dados["vendas"]["vendido"]) == Decimal("80.00")
    assert dados["vendas"]["pedidos_pagos"] == 2
    assert Decimal(dados["vendas"]["ticket_medio"]) == Decimal("40.00")
    formas = {f["forma"]: Decimal(f["valor"]) for f in dados["formas_de_pagamento"]}
    assert formas == {"Dinheiro": Decimal("40.00"), "PIX": Decimal("40.00")}
    (caixa,) = dados["caixas_abertos"]
    assert caixa["caixa"] == "Caixa 1"
    assert Decimal(caixa["saldo"]) == Decimal("140.00")  # abertura 100 + 40 em dinheiro
    assert dados["produtos_vendidos"][0]["produto"] == "Prato"
    assert [b["rotulo"] for b in dados["grafico"]] == [f"{timezone.localtime().hour:02d}h"]


def test_o_que_nao_tem_valor_nao_vem(api_client, restaurant, loja):
    vendas = api_client.get(URL, {"restaurant": str(restaurant.pk)}).json()["vendas"]

    assert "pedidos_cancelados" not in vendas and "descontos" not in vendas
    assert "baixas_de_estoque" not in api_client.get(URL, {"restaurant": str(restaurant.pk)}).json()


def test_semana_e_mes_somam_os_dias_anteriores(api_client, restaurant, loja):
    vender, dinheiro = loja
    hoje = timezone.localdate()
    if hoje.weekday() == 0 or hoje.day == 1:
        pytest.skip("hoje é o primeiro dia da semana ou do mês: não há dia anterior no período")
    vender(dinheiro, quando=timezone.now() - timedelta(days=1))

    dia = api_client.get(URL, {"restaurant": str(restaurant.pk)}).json()
    semana = api_client.get(URL, {"restaurant": str(restaurant.pk), "periodo": "semana"}).json()

    assert Decimal(dia["vendas"]["vendido"]) == Decimal("80.00")
    assert Decimal(semana["vendas"]["vendido"]) == Decimal("120.00")
    assert len(semana["grafico"]) == 2  # um dia por barra: ontem e hoje


def test_periodo_desconhecido_vira_o_dia(api_client, restaurant, loja):
    dados = api_client.get(URL, {"restaurant": str(restaurant.pk), "periodo": "ano"}).json()

    assert dados["periodo"]["nome"] == "dia"
