"""Todo jeito de RECEBER, pela API — e o que tem de sobrar depois.

Cada caminho termina em `conferir_tudo_fechado`, que olha os quatro estados
que o recebimento move ao mesmo tempo: o pedido, as anotações dos cartões, o
cartão e a mesa. Conferir só o status do pedido deixaria os outros três
passarem — e é sempre um deles que aparece no salão no dia seguinte.

As recusas e as saídas sem pagar estão em `test_matriz_de_pagamento_recusas`.
"""
from decimal import Decimal

import pytest

from apps.orders.models import Order
from apps.payments.models import PaymentMethod

from .conftest import ROTA, criar_com_item, ler, pagar
from .matriz_conta import abrir_conta, comanda_com_consumo, conferir_tudo_fechado


pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario(contexto_tenant, restaurant, sem_caixa_obrigatorio):
    return restaurant


@pytest.fixture
def cartao(cenario, account, restaurant, branch, manager_user, produto, mesa):
    """Um cartão com 50,00 de consumo, sentado na mesa."""
    return comanda_com_consumo(
        account=account, restaurant=restaurant, branch=branch,
        user=manager_user, produto=produto, mesa=mesa, quantidade=2,
    )


@pytest.fixture
def conta(api_client, restaurant, cartao):
    return abrir_conta(api_client, restaurant=restaurant, cartoes=[cartao])


@pytest.fixture
def credito(account, restaurant, branch):
    return PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Crédito", method_type=PaymentMethod.TYPE_CARD,
    )


def test_receber_o_valor_exato_fecha_TUDO(conta, api_client, cartao, mesa, dinheiro):
    recebido = pagar(api_client, conta, dinheiro, "50.00")

    assert recebido.status_code == 201, recebido.data
    conferir_tudo_fechado(api_client, conta, cartao=cartao, mesa=mesa)


def test_dinheiro_a_mais_vira_TROCO_e_nao_venda(
    conta, api_client, cartao, mesa, dinheiro
):
    """O cliente paga 100 numa conta de 50. A venda é 50; 50 voltam para ele."""
    recebido = pagar(api_client, conta, dinheiro, "100.00")

    assert recebido.status_code == 201, recebido.data
    assert Decimal(recebido.data["amount"]) == Decimal("50.00")
    assert Decimal(recebido.data["change_amount"]) == Decimal("50.00")
    conferir_tudo_fechado(api_client, conta, cartao=cartao, mesa=mesa)


def test_dois_recebimentos_parciais_fecham_a_conta(
    conta, api_client, cartao, mesa, dinheiro
):
    """O primeiro NÃO pode fechar: metade paga é conta aberta."""
    from apps.restaurants.models import Command

    primeiro = pagar(api_client, conta, dinheiro, "20.00")

    assert primeiro.status_code == 201, primeiro.data
    assert ler(api_client, conta)["status"] != Order.STATUS_PAID
    cartao.refresh_from_db()
    assert cartao.status == Command.STATUS_OCCUPIED, (
        "o cartão foi liberado com a conta pela metade"
    )

    pagar(api_client, conta, dinheiro, "30.00")
    conferir_tudo_fechado(api_client, conta, cartao=cartao, mesa=mesa)


def test_metodos_DIFERENTES_na_mesma_conta(
    conta, api_client, cartao, mesa, dinheiro, credito
):
    """Metade no dinheiro, metade no cartão — a conta mais comum da mesa."""
    pagar(api_client, conta, dinheiro, "20.00")
    no_cartao = api_client.post(
        f"{ROTA}/{conta}/pay/",
        {
            "payment_method": str(credito.pk),
            "amount": "30.00",
            "card_subtype": "credit",
        },
        format="json",
    )

    assert no_cartao.status_code == 201, no_cartao.data
    conferir_tudo_fechado(api_client, conta, cartao=cartao, mesa=mesa)
    assert len(api_client.get(f"{ROTA}/{conta}/payments/").data) == 2


def test_a_mesma_chave_NAO_cobra_duas_vezes(conta, api_client, dinheiro):
    """A rede caiu depois de gravar: o PDV reenvia o mesmo recebimento."""
    primeiro = pagar(api_client, conta, dinheiro, "50.00", chave="terminal-1-abc")
    repetido = pagar(api_client, conta, dinheiro, "50.00", chave="terminal-1-abc")

    assert primeiro.status_code == 201
    assert repetido.status_code == 201
    assert primeiro.data["id"] == repetido.data["id"]
    assert len(api_client.get(f"{ROTA}/{conta}/payments/").data) == 1


def test_a_taxa_de_servico_entra_ANTES_de_receber(
    conta, api_client, cartao, mesa, dinheiro, restaurant
):
    """Fechar a conta aplica a taxa; o total a receber é o que saiu do fechar."""
    restaurant.default_service_fee_percent = Decimal("10.00")
    restaurant.save(update_fields=["default_service_fee_percent"])

    fechada = api_client.post(
        f"{ROTA}/{conta}/close/", {"service_fee_enabled": True}, format="json"
    )
    assert fechada.status_code == 200, fechada.data
    assert Decimal(fechada.data["total"]) == Decimal("55.00")

    pagar(api_client, conta, dinheiro, fechada.data["total"])
    conferir_tudo_fechado(api_client, conta, cartao=cartao, mesa=mesa)


def test_a_conta_de_QUATRO_cartoes_libera_os_quatro(
    cenario, api_client, account, restaurant, branch, manager_user, produto, mesa,
    dinheiro,
):
    """A mesa da família: o caso central, não a exceção."""
    from apps.restaurants.models import Command, Table

    quatro = [
        comanda_com_consumo(
            account=account, restaurant=restaurant, branch=branch,
            user=manager_user, produto=produto, mesa=mesa,
        )
        for _ in range(4)
    ]
    conta = abrir_conta(api_client, restaurant=restaurant, cartoes=quatro)

    recebido = pagar(api_client, conta, dinheiro, "100.00")

    assert recebido.status_code == 201, recebido.data
    for cartao in quatro:
        cartao.refresh_from_db()
        assert cartao.status == Command.STATUS_FREE
        assert cartao.current_table_id is None
    mesa.refresh_from_db()
    assert mesa.status == Table.STATUS_FREE


def test_o_balcao_pago_nao_mexe_em_cartao_nem_mesa(
    cenario, api_client, restaurant, produto, dinheiro
):
    """Sem comanda não há o que liberar — e o caminho não pode quebrar nisso."""
    pedido = criar_com_item(
        api_client, restaurant=restaurant, produto=produto, tipo=Order.TYPE_COUNTER
    )

    recebido = pagar(api_client, pedido.data["id"], dinheiro, "25.00")

    assert recebido.status_code == 201, recebido.data
    assert ler(api_client, pedido.data["id"])["status"] == Order.STATUS_PAID
