"""Todas as portas por onde um pedido NASCE, pela API de verdade.

As regras já tinham cobertura no nível de serviço — e ela passava inteira
enquanto `create-with-item` recusava a conta agrupada com 400. O defeito
estava na PORTA, não na regra, e nenhum teste passava pela porta.

As quatro portas:

* `create-with-item` — balcão, entrega, retirada e a comanda do garçom: o
  pedido nasce com o primeiro item, na mesma transação;
* `POST /orders/` — o pedido vazio, que é como a conta só de comandas abre;
* `POST /orders/{id}/items/` — o segundo item em diante;
* `POST /orders/{id}/attach-commands/` — o consumo que os cartões juntaram.

As recusas estão no arquivo vizinho, `test_matriz_de_criacao_recusas.py`.
"""
from decimal import Decimal

import pytest

from apps.orders.models import Order
from apps.restaurants.models import Command

from .conftest import anexar, criar_com_item, criar_vazio, incluir_item, ler
from .matriz_conta import comanda_com_consumo


pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario(contexto_tenant, restaurant, sem_caixa_obrigatorio):
    return restaurant


@pytest.fixture
def cartoes(cenario, account, restaurant, branch, manager_user, produto):
    def criar(quantos, mesa=None):
        return [
            comanda_com_consumo(
                account=account, restaurant=restaurant, branch=branch,
                user=manager_user, produto=produto, mesa=mesa,
            )
            for _ in range(quantos)
        ]

    return criar


@pytest.mark.parametrize(
    "tipo", [Order.TYPE_COUNTER, Order.TYPE_TAKEAWAY, Order.TYPE_DELIVERY]
)
def test_o_pedido_de_balcao_entrega_e_retirada_nasce_com_o_item(
    cenario, api_client, restaurant, produto, tipo
):
    """Os três tipos sem mesa nem cartão: uma chamada, pedido e item."""
    resposta = criar_com_item(
        api_client, restaurant=restaurant, produto=produto, tipo=tipo
    )

    assert resposta.status_code == 201, resposta.data
    assert resposta.data["order_type"] == tipo
    assert Decimal(resposta.data["total"]) == Decimal("25.00")
    assert resposta.data["created_item_id"]


def test_a_conta_da_MESA_e_do_tipo_comanda_e_CARREGA_a_mesa(
    cenario, api_client, restaurant, produto, mesa
):
    """O tipo `table` foi aposentado: a mesa é uma conta de comandas COM mesa.

    E a mesa precisa chegar ao pedido. `create-with-item` a conferia e depois
    a descartava: a chamada dizia "esta conta é da mesa 1", o servidor
    concordava e gravava o pedido sem mesa nenhuma — cupom sem origem e
    `free_table_if_empty(order.table)` sem o que liberar no pagamento.
    """
    criado = criar_com_item(
        api_client, restaurant=restaurant, produto=produto,
        tipo=Order.TYPE_COMMAND, quantidade=2, table=str(mesa.pk),
    )

    assert criado.status_code == 201, criado.data
    assert str(criado.data["table"]) == str(mesa.pk)
    assert Decimal(criado.data["total"]) == Decimal("50.00")


def test_a_conta_SO_de_comandas_soma_o_que_os_cartoes_anotaram(
    cenario, api_client, restaurant, cartoes, mesa
):
    """A mesa que chega no caixa sem nada novo para passar."""
    tres = cartoes(3, mesa=mesa)

    pedido = criar_vazio(api_client, restaurant=restaurant, tipo=Order.TYPE_COMMAND)
    assert pedido.status_code == 201, pedido.data
    puxou = anexar(api_client, pedido.data["id"], [c.pk for c in tres])

    assert puxou.status_code == 200, puxou.data
    assert Decimal(puxou.data["total"]) == Decimal("75.00")


def test_a_conta_de_comandas_ACEITA_item_passado_no_caixa(
    cenario, api_client, restaurant, cartoes, produto_barato
):
    """O defeito de produção: 400 'Selecione uma comanda válida'.

    A mesa chega com dois cartões e o cliente pede mais uma cerveja. O tipo é
    `command` — é o que o relatório agrupa —, mas não existe "a" comanda deste
    pedido: elas entram depois, e podem ser duzentas.
    """
    dois = cartoes(2)

    pedido = criar_com_item(
        api_client, restaurant=restaurant, produto=produto_barato,
        tipo=Order.TYPE_COMMAND,
    )
    assert pedido.status_code == 201, pedido.data
    assert pedido.data["command"] is None

    puxou = anexar(api_client, pedido.data["id"], [c.pk for c in dois])
    assert puxou.status_code == 200, puxou.data
    # Os dois cartões (25,00 cada) mais a cerveja passada no caixa.
    assert Decimal(puxou.data["total"]) == Decimal("60.05")


def test_o_item_seguinte_entra_na_conta_que_ja_tem_cartao(
    cenario, api_client, restaurant, cartoes, produto_barato
):
    """Passar o SEGUNDO item não pode ser diferente de passar o primeiro."""
    pedido = criar_vazio(api_client, restaurant=restaurant, tipo=Order.TYPE_COMMAND)
    anexar(api_client, pedido.data["id"], [c.pk for c in cartoes(1)])

    incluido = incluir_item(api_client, pedido.data["id"], produto_barato)

    assert incluido.status_code in (200, 201), incluido.data
    assert Decimal(ler(api_client, pedido.data["id"])["total"]) == Decimal("35.05")


def test_a_comanda_do_garcom_continua_abrindo_o_pedido_DELA(
    cenario, api_client, account, restaurant, branch, produto
):
    """O app do garçom manda o cartão que leu, e isso não mudou."""
    cartao = Command.objects.create(
        account=account, restaurant=restaurant, branch=branch
    )

    resposta = criar_com_item(
        api_client, restaurant=restaurant, produto=produto,
        tipo=Order.TYPE_COMMAND, command=str(cartao.pk),
    )

    assert resposta.status_code == 201, resposta.data
    assert str(resposta.data["command"]) == str(cartao.pk)


def test_o_mesmo_cartao_duas_vezes_NAO_cobra_em_dobro(
    cenario, api_client, restaurant, cartoes
):
    """O caixa toca duas vezes, ou dois terminais mandam junto."""
    cartao = cartoes(1)[0]
    pedido = criar_vazio(api_client, restaurant=restaurant, tipo=Order.TYPE_COMMAND)
    anexar(api_client, pedido.data["id"], [cartao.pk])

    # A segunda é recusada porque não sobrou anotação nova — e o total fica.
    anexar(api_client, pedido.data["id"], [cartao.pk])

    assert Decimal(ler(api_client, pedido.data["id"])["total"]) == Decimal("25.00")
