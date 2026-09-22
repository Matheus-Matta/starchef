"""O que o recebimento RECUSA, e as duas saídas sem pagar.

Uma conta aberta tem três destinos: recebida, cancelada, ou devolvida aos
cartões. Os dois últimos parecem o mesmo gesto para o operador — "não vou
cobrar isso agora" — e são opostos no relatório:

* **cancelar** diz que a venda não aconteceu: o consumo sai como PERDA, e por
  isso exige senha de gerente;
* **soltar os cartões** (`detach-commands`) diz que só a CONTA foi desfeita: o
  consumo volta a pendente, o cartão volta a estar em uso, e ninguém precisa
  de senha porque nada se perdeu.

É a distinção que o PDV desktop usa ao sair do pagamento sem concluir. Se um
dia os dois se confundirem, os testes daqui caem.
"""
import pytest

from apps.orders.command_items import launch_item
from apps.orders.models_command_item import CommandItem
from apps.restaurants.models import Command, Table

from .conftest import ROTA, anexar, pagar
from .matriz_conta import abrir_conta, anotacoes_de, comanda_com_consumo


pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario(contexto_tenant, restaurant, sem_caixa_obrigatorio):
    return restaurant


@pytest.fixture
def cartao(cenario, account, restaurant, branch, manager_user, produto, mesa):
    return comanda_com_consumo(
        account=account, restaurant=restaurant, branch=branch,
        user=manager_user, produto=produto, mesa=mesa, quantidade=2,
    )


@pytest.fixture
def conta(api_client, restaurant, cartao):
    return abrir_conta(api_client, restaurant=restaurant, cartoes=[cartao])


def test_conta_paga_nao_recebe_de_novo(conta, api_client, dinheiro):
    pagar(api_client, conta, dinheiro, "50.00")

    outra_vez = pagar(api_client, conta, dinheiro, "50.00")

    assert outra_vez.status_code == 400


def test_conta_paga_nao_aceita_mais_cartoes(
    conta, api_client, account, restaurant, branch, manager_user, produto, dinheiro
):
    """Anexar depois do pagamento cobraria um consumo que ninguém recebeu."""
    pagar(api_client, conta, dinheiro, "50.00")
    outro = Command.objects.create(
        account=account, restaurant=restaurant, branch=branch
    )
    launch_item(command=outro, product=produto, user=manager_user, quantity=1)

    recusa = anexar(api_client, conta, [outro.pk])

    assert recusa.status_code == 409


def test_receber_sem_forma_de_pagamento_e_erro_de_preenchimento(conta, api_client):
    """Lido com `[]` isto virava 500, e o PDV reenfileirava para sempre."""
    recusa = api_client.post(f"{ROTA}/{conta}/pay/", {"amount": "50.00"}, format="json")

    assert recusa.status_code == 400


def test_receber_sem_valor_e_erro_de_preenchimento(conta, api_client, dinheiro):
    recusa = api_client.post(
        f"{ROTA}/{conta}/pay/",
        {"payment_method": str(dinheiro.pk)},
        format="json",
    )

    assert recusa.status_code == 400


def test_cancelar_a_conta_EXIGE_autorizacao(conta, api_client):
    """Cancelar venda é gesto de gerente, e continua sendo."""
    recusa = api_client.post(
        f"{ROTA}/{conta}/cancel/", {"reason": "Cliente desistiu"}, format="json"
    )

    assert recusa.status_code == 403


def test_cancelar_autorizado_solta_o_salao_e_marca_PERDA(
    conta, api_client, cartao, mesa, restaurant
):
    """Cancelar é dizer que aquela venda não aconteceu."""
    from django.contrib.auth.hashers import make_password

    restaurant.cash_action_password = make_password("senha-operacao")
    restaurant.save(update_fields=["cash_action_password", "updated_at"])

    cancelada = api_client.post(
        f"{ROTA}/{conta}/cancel/",
        {"reason": "Cliente desistiu", "cash_password": "senha-operacao"},
        format="json",
    )

    assert cancelada.status_code == 200, cancelada.data
    cartao.refresh_from_db()
    mesa.refresh_from_db()
    assert cartao.status == Command.STATUS_FREE
    assert cartao.current_table_id is None
    assert mesa.status == Table.STATUS_FREE
    assert anotacoes_de(cartao) == {CommandItem.STATUS_CANCELADO}


def test_soltar_os_cartoes_NAO_pede_senha_e_NAO_marca_perda(
    conta, api_client, cartao, restaurant
):
    """A saída do operador que só desistiu do pagamento agora.

    É o que o PDV desktop faz ao deixar a tela de pagamento sem concluir. Sem
    isto, a conta ficava aberta segurando o consumo e a comanda parecia
    travada — com os itens à vista e o servidor recusando cobrá-la.
    """
    devolvida = api_client.post(
        f"{ROTA}/{conta}/detach-commands/",
        {"commands": [str(cartao.pk)]},
        format="json",
    )

    assert devolvida.status_code == 200, devolvida.data
    assert anotacoes_de(cartao) == {CommandItem.STATUS_PENDENTE}
    cartao.refresh_from_db()
    assert cartao.status == Command.STATUS_OCCUPIED


def test_cartao_solto_PODE_ser_cobrado_numa_conta_nova(
    conta, api_client, cartao, mesa, restaurant, dinheiro
):
    """O que o operador quer: tentar de novo e a conta abrir."""
    from .matriz_conta import conferir_tudo_fechado

    api_client.post(
        f"{ROTA}/{conta}/detach-commands/",
        {"commands": [str(cartao.pk)]},
        format="json",
    )

    nova = abrir_conta(api_client, restaurant=restaurant, cartoes=[cartao])
    recebido = pagar(api_client, nova, dinheiro, "50.00")

    assert recebido.status_code == 201, recebido.data
    conferir_tudo_fechado(api_client, nova, cartao=cartao, mesa=mesa)
