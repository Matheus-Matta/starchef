"""Entrar no pagamento não avança o pedido; o primeiro recebimento sim.

A tela de venda chamava `/close/` só para abrir o pagamento, e o pedido virava
"aguardando pagamento" sem ninguém ter pago nada — voltar à venda deixava o
pedido nesse estado, e as escolhas (taxa, CPF) se perdiam na tela.

Agora `/checkout/` grava as escolhas e recalcula o total, com o pedido ABERTO.
Quem muda o estado é o dinheiro: o primeiro recebimento leva a "aguardando"
(parcial) ou "pago"; tirar o último devolve a "aberto", sem apagar as escolhas.
`/close/` continua como era, para o PDV desktop e o app.
"""
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import PaymentMethod

pytestmark = pytest.mark.django_db

CPF = "52998224725"


@pytest.fixture
def pedido(contexto_tenant, restaurant, branch, manager_user, produto, sem_caixa_obrigatorio):
    restaurant.default_service_fee_percent = Decimal("10.00")
    restaurant.save(update_fields=["default_service_fee_percent"])
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=2, user=manager_user)  # R$ 50
    pedido.refresh_from_db()
    return pedido


@pytest.fixture
def dinheiro(account, restaurant, branch):
    return PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Dinheiro", method_type=PaymentMethod.TYPE_CASH
    )


def _checkout(cliente, pedido, **corpo):
    resposta = cliente.post(f"/api/v1/orders/{pedido.pk}/checkout/", corpo, format="json")
    assert resposta.status_code == 200, resposta.content
    return resposta.data


def _pagar(cliente, pedido, metodo, valor):
    resposta = cliente.post(
        f"/api/v1/orders/{pedido.pk}/pay/", {"payment_method": str(metodo.pk), "amount": valor}, format="json"
    )
    assert resposta.status_code in (200, 201), resposta.content
    return resposta.data


def test_checkout_grava_escolhas_e_deixa_o_pedido_aberto(api_client, pedido):
    dados = _checkout(api_client, pedido, service_fee_enabled=True, fiscal_customer_cpf=CPF)

    assert dados["status"] == Order.STATUS_OPEN
    assert dados["payment_status"] == Order.PAYMENT_PENDING
    assert Decimal(dados["service_fee"]) == Decimal("5.00")
    assert Decimal(dados["total"]) == Decimal("55.00")
    pedido.refresh_from_db()
    assert pedido.fiscal_customer_cpf == CPF
    assert pedido.service_fee_enabled is True
    assert pedido.closed_at is None


def test_voltar_a_venda_e_entrar_de_novo_mantem_as_escolhas(api_client, pedido, produto, manager_user):
    _checkout(api_client, pedido, service_fee_enabled=True, fiscal_customer_cpf=CPF)
    add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)

    dados = api_client.get(f"/api/v1/orders/{pedido.pk}/").data

    assert dados["status"] == Order.STATUS_OPEN
    assert dados["fiscal_customer_cpf"] == CPF
    assert dados["service_fee_enabled"] is True
    # A taxa acompanha o item novo: 10% de R$ 75.
    assert Decimal(dados["service_fee"]) == Decimal("7.50")


def test_cpf_invalido_e_recusado(api_client, pedido):
    resposta = api_client.post(f"/api/v1/orders/{pedido.pk}/checkout/", {"fiscal_customer_cpf": "11111111111"}, format="json")

    assert resposta.status_code == 400


def test_primeiro_recebimento_avanca_e_o_ultimo_removido_devolve_a_aberto(api_client, pedido, dinheiro):
    _checkout(api_client, pedido, service_fee_enabled=True, fiscal_customer_cpf=CPF)

    _pagar(api_client, pedido, dinheiro, "20.00")
    pedido.refresh_from_db()
    assert (pedido.status, pedido.payment_status) == (Order.STATUS_AWAITING_PAYMENT, Order.PAYMENT_PARTIAL)

    with tenant_context(pedido.account):
        pagamento = pedido.payments.get()
    api_client.delete(f"/api/v1/orders/{pedido.pk}/payments/{pagamento.pk}/")
    pedido.refresh_from_db()
    assert (pedido.status, pedido.payment_status) == (Order.STATUS_OPEN, Order.PAYMENT_PENDING)
    assert pedido.closed_at is None
    # As escolhas do pagamento continuam lá para a próxima tentativa.
    assert pedido.fiscal_customer_cpf == CPF
    assert pedido.service_fee_enabled is True


def test_remover_um_de_dois_recebimentos_continua_aguardando(api_client, pedido, dinheiro):
    _checkout(api_client, pedido)
    _pagar(api_client, pedido, dinheiro, "10.00")
    _pagar(api_client, pedido, dinheiro, "10.00")
    with tenant_context(pedido.account):
        primeiro = pedido.payments.order_by("created_at").first()

    api_client.delete(f"/api/v1/orders/{pedido.pk}/payments/{primeiro.pk}/")
    pedido.refresh_from_db()

    assert (pedido.status, pedido.payment_status) == (Order.STATUS_AWAITING_PAYMENT, Order.PAYMENT_PARTIAL)


def test_pagar_tudo_quita(api_client, pedido, dinheiro):
    total = _checkout(api_client, pedido)["total"]

    _pagar(api_client, pedido, dinheiro, total)
    pedido.refresh_from_db()

    assert (pedido.status, pedido.payment_status) == (Order.STATUS_PAID, Order.PAYMENT_PAID)


def test_close_continua_como_era_para_desktop_e_app(api_client, pedido):
    resposta = api_client.post(f"/api/v1/orders/{pedido.pk}/close/", {"service_fee_enabled": False}, format="json")

    assert resposta.data["status"] == Order.STATUS_AWAITING_PAYMENT
