"""Desconto na venda inteira: o caixa libera com a senha, no mesmo envio.

O `/close/` aceitava a senha de ações do caixa para aprovar o desconto, mas o
`/orders/submit/` (a venda nova num envio só) não a repassava: o caixa que
não é gerente recebia "precisa da aprovação de um gerente" para SEMPRE, com ou
sem a senha certa. Com o desconto na tela de pagamento, era o caminho comum.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.hashers import make_password

from apps.orders.models import Order
from apps.orders.tests.test_desconto_aprovado import caixa  # noqa: F401
from apps.orders.tests.test_venda_inteira import URL, _venda

pytestmark = pytest.mark.django_db


@pytest.fixture
def senha_do_caixa(restaurant):
    restaurant.cash_action_password = make_password("1234")
    restaurant.save(update_fields=["cash_action_password"])


def _com_desconto(restaurant, produto, **extra):
    return {**_venda(restaurant, produto), "simular": True,
            "close": {"discount": "10.00", "service_fee_enabled": False}, **extra}


def test_caixa_sem_senha_recebe_o_pedido_de_aprovacao(
    caixa, contexto_tenant, sem_caixa_obrigatorio, senha_do_caixa, restaurant, produto  # noqa: F811
):
    resposta = caixa.post(URL, _com_desconto(restaurant, produto), format="json")

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "discount_authorization_required"


def test_caixa_com_a_senha_certa_tem_o_desconto_aprovado(
    caixa, contexto_tenant, sem_caixa_obrigatorio, senha_do_caixa, restaurant, produto, dinheiro  # noqa: F811
):
    simulado = caixa.post(URL, _com_desconto(restaurant, produto, cash_password="1234"),
                          format="json")
    assert simulado.status_code == 200, simulado.content
    assert Decimal(simulado.json()["order"]["total"]) == Decimal("40.00")

    corpo = {**_venda(restaurant, produto, dinheiro, valor="40.00"),
             "close": {"discount": "10.00", "service_fee_enabled": False},
             "cash_password": "1234"}
    resposta = caixa.post(URL, corpo, format="json")

    assert resposta.status_code == 201, resposta.content
    pedido = Order.all_objects.get(pk=corpo["id"])
    assert pedido.discount == Decimal("10.00")
    assert pedido.discount_authorization == Order.AUTHORIZATION_CASH_PASSWORD


def test_senha_errada_continua_recusando(
    caixa, contexto_tenant, sem_caixa_obrigatorio, senha_do_caixa, restaurant, produto  # noqa: F811
):
    resposta = caixa.post(URL, _com_desconto(restaurant, produto, cash_password="9999"),
                          format="json")

    assert resposta.status_code == 403
