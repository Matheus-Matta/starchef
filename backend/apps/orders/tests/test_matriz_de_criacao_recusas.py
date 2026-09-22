"""O que a abertura de pedido RECUSA — e com que código.

A metade que não passa importa tanto quanto a que passa, e por um motivo
prático: o PDV trata 400 como erro de preenchimento (mostra e para) e 409 como
conflito de estado (mostra e deixa recarregar). Trocar um pelo outro faz o
terminal reenviar o mesmo corpo para sempre, ou desistir de algo que só
precisava de um F5.
"""
import pytest

from apps.orders.models import Order
from apps.restaurants.models import Command

from .conftest import anexar, criar_com_item, criar_vazio
from .matriz_conta import comanda_com_consumo


pytestmark = pytest.mark.django_db

INEXISTENTE = "d3f0a0f2-0000-4000-8000-000000000000"


@pytest.fixture
def cenario(contexto_tenant, restaurant, sem_caixa_obrigatorio):
    return restaurant


def test_o_tipo_table_APOSENTADO_e_recusado(cenario, api_client, restaurant, produto):
    """Aceitá-lo criaria pedidos que nenhuma tela de hoje sabe abrir."""
    recusa = criar_com_item(
        api_client, restaurant=restaurant, produto=produto, tipo=Order.TYPE_TABLE
    )

    assert recusa.status_code == 400


def test_tipo_de_pedido_invalido_e_erro_de_preenchimento(
    cenario, api_client, restaurant, produto
):
    recusa = criar_com_item(
        api_client, restaurant=restaurant, produto=produto, tipo="jantar"
    )

    assert recusa.status_code == 400


def test_mesa_INVENTADA_na_conta_e_recusada(cenario, api_client, restaurant, produto):
    recusa = criar_com_item(
        api_client, restaurant=restaurant, produto=produto,
        tipo=Order.TYPE_COMMAND, table=INEXISTENTE,
    )

    assert recusa.status_code == 400


def test_comanda_INVENTADA_e_recusada(cenario, api_client, restaurant, produto):
    """Aceitar um id inválido lançaria o item num cartão que ninguém escolheu.

    É o contraponto do conserto que tornou `command` OPCIONAL: ausente vale
    (conta agrupada), errado não.
    """
    recusa = criar_com_item(
        api_client, restaurant=restaurant, produto=produto,
        tipo=Order.TYPE_COMMAND, command=INEXISTENTE,
    )

    assert recusa.status_code == 400


def test_pedido_sem_item_nenhum_e_recusado(cenario, api_client, restaurant):
    """`create-with-item` sem item não tem o que criar."""
    recusa = api_client.post(
        "/api/v1/orders/create-with-item/",
        {"order_type": Order.TYPE_COUNTER, "restaurant": str(restaurant.pk)},
        format="json",
    )

    assert recusa.status_code == 400


def test_produto_INVENTADO_e_recusado(cenario, api_client, restaurant):
    recusa = api_client.post(
        "/api/v1/orders/create-with-item/",
        {
            "order_type": Order.TYPE_COUNTER,
            "restaurant": str(restaurant.pk),
            "item": {"product": INEXISTENTE, "quantity": 1},
        },
        format="json",
    )

    assert recusa.status_code == 400


def test_anexar_sem_comanda_nenhuma_e_erro_de_preenchimento(
    cenario, api_client, restaurant
):
    pedido = criar_vazio(api_client, restaurant=restaurant, tipo=Order.TYPE_COMMAND)

    recusa = anexar(api_client, pedido.data["id"], [])

    assert recusa.status_code == 400


def test_cartao_sem_consumo_nao_entra_na_conta(
    cenario, api_client, account, restaurant, branch
):
    """Anexá-lo produziria uma venda presa a um cartão que ninguém está usando.

    409, e não 400: o corpo está certo — o que não serve é o ESTADO do cartão.
    """
    vazio = Command.objects.create(
        account=account, restaurant=restaurant, branch=branch
    )
    pedido = criar_vazio(api_client, restaurant=restaurant, tipo=Order.TYPE_COMMAND)

    recusa = anexar(api_client, pedido.data["id"], [vazio.pk])

    assert recusa.status_code == 409
    assert "não tem item pendente" in str(recusa.data)


def test_cartao_preso_em_outra_conta_DIZ_isso(
    cenario, api_client, account, restaurant, branch, manager_user, produto
):
    """A frase que custou o diagnóstico: ele TEM item pendente, à vista.

    Dizer "não tem item pendente" para um operador que está olhando os itens
    na tela manda ele procurar no lugar errado. A causa é a conta anterior,
    aberta e nunca concluída.
    """
    cartao = comanda_com_consumo(
        account=account, restaurant=restaurant, branch=branch,
        user=manager_user, produto=produto,
    )
    primeira = criar_vazio(api_client, restaurant=restaurant, tipo=Order.TYPE_COMMAND)
    anexar(api_client, primeira.data["id"], [cartao.pk])

    segunda = criar_vazio(api_client, restaurant=restaurant, tipo=Order.TYPE_COMMAND)
    recusa = anexar(api_client, segunda.data["id"], [cartao.pk])

    assert recusa.status_code == 409
    assert "outra conta aberta" in str(recusa.data)


def test_comanda_INEXISTENTE_na_conta_e_recusada(cenario, api_client, restaurant):
    pedido = criar_vazio(api_client, restaurant=restaurant, tipo=Order.TYPE_COMMAND)

    recusa = anexar(api_client, pedido.data["id"], [INEXISTENTE])

    assert recusa.status_code == 409
