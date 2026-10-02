"""Uma conta com consumo não pode ser excluída — e a excluída não prende cartão.

Produção, 01/10/2026, pico de 500 comandas: "A comanda 98 já está na conta ,
que continua aberta" — com o número da conta EM BRANCO. A conta que segurava o
cartão tinha sido excluída.

O caminho: ao sair de um pedido, o PDV varre os pedidos abertos e apaga os que
vê vazios. O caixa A abre a conta agrupada; o terminal B lista e a vê vazia; A
anexa as comandas; B manda o DELETE. O servidor só recusava exclusão com nota
ou pagamento, e apagava a conta já cheia. Com o limite de requisições segurando
cada chamada por até 46 s, essa janela ficou enorme.

O cartão ficava preso para sempre: a trava procurava a conta entre os itens
(que continuavam lá) e o número dela no manager que esconde os excluídos.
"""
import pytest
from django.core.exceptions import ValidationError

from apps.core.tenant import tenant_context
from apps.orders.command_billing import attach_commands_to_order
from apps.orders.command_items import launch_item
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


@pytest.fixture
def comanda(account, restaurant, branch):
    return Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=98)


def _conta(restaurant, branch, usuario):
    return create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND, user=usuario)


def test_excluir_conta_aberta_com_consumo_e_recusado(
    api_client, contexto_tenant, restaurant, branch, manager_user, comanda, produto, sem_caixa_obrigatorio,
):
    launch_item(command=comanda, product=produto, user=manager_user, quantity=1)
    conta = _conta(restaurant, branch, manager_user)
    attach_commands_to_order(order=conta, command_ids=[comanda.pk], user=manager_user)

    resposta = api_client.delete(f"/api/v1/orders/{conta.pk}/")

    assert resposta.status_code == 409, resposta.content
    with tenant_context(restaurant.account):
        assert Order.objects.filter(pk=conta.pk).exists()


def test_rascunho_vazio_continua_podendo_ser_excluido(
    api_client, contexto_tenant, restaurant, branch, manager_user, sem_caixa_obrigatorio,
):
    """A varredura de rascunhos órfãos é legítima — só não pode levar conta cheia."""
    rascunho = _conta(restaurant, branch, manager_user)

    assert api_client.delete(f"/api/v1/orders/{rascunho.pk}/").status_code == 204


def test_anexar_comanda_a_conta_ja_excluida_e_recusado(
    contexto_tenant, restaurant, branch, manager_user, comanda, produto, sem_caixa_obrigatorio,
):
    """O outro lado da corrida: o DELETE chegou primeiro."""
    launch_item(command=comanda, product=produto, user=manager_user, quantity=1)
    conta = _conta(restaurant, branch, manager_user)
    conta.delete()

    with pytest.raises(ValidationError):
        attach_commands_to_order(order=conta, command_ids=[comanda.pk], user=manager_user)


def test_conta_excluida_nao_prende_a_comanda(
    contexto_tenant, restaurant, branch, manager_user, comanda, produto, sem_caixa_obrigatorio,
):
    """As comandas presas hoje em produção se soltam sozinhas com a correção."""
    launch_item(command=comanda, product=produto, user=manager_user, quantity=1)
    excluida = _conta(restaurant, branch, manager_user)
    attach_commands_to_order(order=excluida, command_ids=[comanda.pk], user=manager_user)
    Order.objects.filter(pk=excluida.pk).update(deleted_at=excluida.updated_at)

    nova = _conta(restaurant, branch, manager_user)
    itens = attach_commands_to_order(order=nova, command_ids=[comanda.pk], user=manager_user)

    assert len(itens) == 1
    comanda.refresh_from_db()
    assert comanda.em_uso is True
