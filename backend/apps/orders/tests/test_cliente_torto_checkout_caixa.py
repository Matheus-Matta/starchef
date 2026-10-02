"""Checkout, exclusão de item e caixa contra o que um cliente com defeito manda.

Corpo errado é 400 com mensagem, coisa que não existe é 404, estado que não
deixa é 409 — nunca 500 — e, quando a resposta é de erro, nada muda: o total,
o status e o que foi gravado continuam como estavam.
"""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.orders.models import Order, OrderItem
from apps.orders.services import add_order_item, create_order
from apps.payments.models import CashRegister
from apps.payments.services import open_cash_register

pytestmark = pytest.mark.django_db


@pytest.fixture
def pedido(contexto_tenant, restaurant, branch, manager_user, produto, sem_caixa_obrigatorio):
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=2, user=manager_user)
    pedido.refresh_from_db()
    return pedido


def _foto(pedido):
    with tenant_context(pedido.account):
        p = Order.objects.get(pk=pedido.pk)
    return (p.status, p.payment_status, p.total, p.discount, p.service_fee_enabled, p.fiscal_customer_cpf)


@pytest.mark.parametrize("corpo", [
    {"discount": "abc"},
    {"discount": "-5"},
    {"discount": "9999"},
    {"discount": ["1"]},
    {"service_fee": "dez"},
    {"expected_total": "muito"},
    {"fiscal_customer_cpf": "11111111111"},
    {"fiscal_customer_cpf": "123"},
])
def test_checkout_com_corpo_torto_e_400_e_nada_muda(api_client, pedido, corpo):
    antes = _foto(pedido)

    resposta = api_client.post(f"/api/v1/orders/{pedido.pk}/checkout/", corpo, format="json")

    assert resposta.status_code == 400, resposta.content
    assert _foto(pedido) == antes


def test_cupom_inexistente_e_422_coupon_rejected_e_nada_muda(api_client, pedido):
    """422 é o contrato do cupom: o PDV reconhece `coupon_rejected` e mostra a recusa."""
    antes = _foto(pedido)

    resposta = api_client.post(f"/api/v1/orders/{pedido.pk}/checkout/", {"coupon_code": "NAO-EXISTE"}, format="json")

    assert resposta.status_code == 422
    assert resposta.json()["error"]["code"] == "coupon_rejected"
    assert _foto(pedido) == antes


def test_checkout_com_corpo_em_lista_e_400(api_client, pedido):
    assert api_client.post(f"/api/v1/orders/{pedido.pk}/checkout/", ["x"], format="json").status_code == 400


@pytest.mark.parametrize("pk", [str(uuid.uuid4()), "nao-e-uuid"])
def test_checkout_de_pedido_inexistente_e_404(api_client, pedido, pk):
    assert api_client.post(f"/api/v1/orders/{pk}/checkout/", {}, format="json").status_code == 404


def test_checkout_de_pedido_cancelado_e_recusado(api_client, pedido):
    with tenant_context(pedido.account):
        Order.objects.filter(pk=pedido.pk).update(status=Order.STATUS_CANCELLED)

    assert api_client.post(f"/api/v1/orders/{pedido.pk}/checkout/", {}, format="json").status_code in (400, 409)


def test_checkout_com_flag_de_taxa_em_texto(api_client, pedido):
    """O cliente manda "false" em texto — é falso, não "verdadeiro porque não é vazio"."""
    resposta = api_client.post(f"/api/v1/orders/{pedido.pk}/checkout/", {"service_fee_enabled": "false"}, format="json")

    assert resposta.status_code == 200
    assert resposta.data["service_fee_enabled"] is False


def _item(pedido):
    with tenant_context(pedido.account):
        return OrderItem.objects.filter(order=pedido).first()


@pytest.mark.parametrize("corpo", [{}, {"reason": ""}, {"reason": "   "}])
def test_excluir_item_sem_motivo_e_400_e_o_item_fica(api_client, pedido, corpo):
    item = _item(pedido)

    resposta = api_client.delete(f"/api/v1/orders/{pedido.pk}/items/{item.pk}/void/", corpo, format="json")

    assert resposta.status_code == 400, resposta.content
    assert _item(pedido).status != OrderItem.STATUS_CANCELLED


def test_excluir_item_de_outro_pedido_e_404(api_client, pedido, restaurant, branch, manager_user):
    outro = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    item = _item(pedido)

    resposta = api_client.delete(f"/api/v1/orders/{outro.pk}/items/{item.pk}/void/", {"reason": "x"}, format="json")

    assert resposta.status_code == 404
    assert _item(pedido).status != OrderItem.STATUS_CANCELLED


def test_excluir_o_mesmo_item_duas_vezes(api_client, pedido):
    """Repetição depois de a resposta se perder: a segunda diz o que houve, não 500."""
    item = _item(pedido)
    rota = f"/api/v1/orders/{pedido.pk}/items/{item.pk}/void/"

    assert api_client.delete(rota, {"reason": "Desistiu"}, format="json").status_code == 200
    segunda = api_client.delete(rota, {"reason": "Desistiu"}, format="json")

    assert segunda.status_code == 400
    assert "já foi cancelado" in str(segunda.content.decode())


@pytest.mark.parametrize("valor", ["abc", "-0.01", "100.01", "1e9", [], {"v": 1}])
def test_margem_do_caixa_torta_e_400(api_client, restaurant, valor):
    resposta = api_client.patch(f"/api/v1/restaurants/{restaurant.pk}/", {"cash_closing_tolerance": valor}, format="json")

    assert resposta.status_code == 400, resposta.content
    restaurant.refresh_from_db()
    assert restaurant.cash_closing_tolerance == Decimal("0.50")


@pytest.mark.parametrize("valor, gravado", [("0", "0.00"), ("2.5", "2.50"), (1, "1.00")])
def test_margem_do_caixa_valida(api_client, restaurant, valor, gravado):
    assert api_client.patch(f"/api/v1/restaurants/{restaurant.pk}/", {"cash_closing_tolerance": valor}, format="json").status_code == 200
    restaurant.refresh_from_db()
    assert restaurant.cash_closing_tolerance == Decimal(gravado)


@pytest.mark.parametrize("contado", [None, "", "abc", ["10"], "-1"])
def test_fechar_caixa_com_valor_torto_e_400_e_o_caixa_segue_aberto(api_client, restaurant, branch, manager_user, contado):
    with tenant_context(restaurant.account):
        sessao = open_cash_register(restaurant=restaurant, branch=branch, user=manager_user, opening_amount=Decimal("50"))

    corpo = {} if contado is None else {"actual_amount": contado}
    resposta = api_client.post(f"/api/v1/cash-register/{sessao.pk}/close/", corpo, format="json")

    assert resposta.status_code in (400, 403, 409), resposta.content
    with tenant_context(restaurant.account):
        assert CashRegister.objects.get(pk=sessao.pk).status == CashRegister.STATUS_OPEN
