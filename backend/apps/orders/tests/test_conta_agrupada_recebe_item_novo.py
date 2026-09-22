"""A conta que cobra comandas também aceita item passado no caixa.

O caso: a mesa chega com dois cartões e o cliente pede mais uma cerveja no
balcão. O PDV anexa os cartões à conta e passa a cerveja — e o pedido é do
tipo `command`, porque é isso que ele é.

`create-with-item` exigia `command` sempre que o tipo fosse `command`, herança
do modelo antigo em que a comanda ABRIA o pedido. No modelo de hoje a comanda
ANOTA: ela entra na conta por `attach-commands`, depois, e podem ser duzentas.
Não existe "a" comanda do pedido para mandar aqui — e o operador via
"Selecione uma comanda válida" ao passar o segundo item.

O tipo continua sendo `command` de propósito: é o que o relatório agrupa, e
mudar para `counter` porque o corpo não trouxe um id faria a mesma venda
aparecer em duas colunas conforme a ordem dos toques do operador.
"""
import pytest

from apps.orders.models import Order
from apps.restaurants.models import Command


pytestmark = pytest.mark.django_db


def _corpo(restaurant, produto, **extra):
    return {
        "order_type": "command",
        "restaurant": str(restaurant.pk),
        "item": {"product": str(produto.pk), "quantity": 1},
        **extra,
    }


def test_conta_de_comandas_aceita_o_primeiro_item_SEM_id_de_comanda(
    contexto_tenant, api_client, restaurant, produto, sem_caixa_obrigatorio
):
    """O defeito: 400 'Selecione uma comanda válida' na conta agrupada."""
    resposta = api_client.post(
        "/api/v1/orders/create-with-item/", _corpo(restaurant, produto), format="json"
    )

    assert resposta.status_code == 201, resposta.data
    assert resposta.data["order_type"] == Order.TYPE_COMMAND
    assert resposta.data["command"] is None


def test_comanda_informada_continua_sendo_CONFERIDA(
    contexto_tenant, api_client, restaurant, produto, sem_caixa_obrigatorio
):
    """Afrouxar o campo ausente não pode afrouxar o campo errado.

    O app do garçom manda `command` de verdade, e um id de outro restaurante
    (ou inventado) tem de continuar sendo recusado — senão o item vai parar
    num cartão que o operador não escolheu.
    """
    resposta = api_client.post(
        "/api/v1/orders/create-with-item/",
        _corpo(restaurant, produto, command="d3f0a0f2-0000-4000-8000-000000000000"),
        format="json",
    )

    assert resposta.status_code == 400
    assert "comanda" in str(resposta.data).lower()


def test_com_comanda_de_verdade_o_pedido_nasce_LIGADO_a_ela(
    contexto_tenant, api_client, account, restaurant, branch, produto,
    sem_caixa_obrigatorio,
):
    """O caminho do garçom não muda: a comanda informada vira a do pedido."""
    comanda = Command.objects.create(
        account=account, restaurant=restaurant, branch=branch, number=771
    )

    resposta = api_client.post(
        "/api/v1/orders/create-with-item/",
        _corpo(restaurant, produto, command=str(comanda.pk)),
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    assert str(resposta.data["command"]) == str(comanda.pk)
