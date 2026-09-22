"""Sair do pagamento sem concluir não pode prender a comanda.

O caminho: o caixa anexa os cartões, vai para o pagamento, e volta — o cliente
foi buscar o cartão de crédito, outra mesa chamou, qualquer coisa. A conta que
ele abriu não virou venda.

Enquanto ela existir, as anotações daqueles cartões estão DENTRO dela: viraram
`OrderItem` com `command_item` apontando de volta. O cartão continua mostrando
os itens (eles seguem `pending`), mas a tentativa seguinte de cobrar é
recusada — e a recusa dizia "não tem item pendente" para um operador que
estava olhando os itens na tela.

O desfazer é `detach_commands_from_order`, não cancelar a conta: cancelar
marcaria o consumo como PERDA. A comida foi comida; quem desistiu foi a conta.
"""
import uuid
from decimal import Decimal

import pytest

from apps.orders.command_billing import (
    attach_commands_to_order,
    detach_commands_from_order,
)
from apps.orders.command_items import launch_item
from apps.orders.models import Order
from apps.orders.models_command_item import CommandItem
from apps.orders.services import create_order
from apps.restaurants.models import Command


pytestmark = pytest.mark.django_db


@pytest.fixture
def comanda(account, restaurant, branch):
    return Command.objects.create(
        account=account, restaurant=restaurant, branch=branch, number=933
    )


@pytest.fixture
def conta_abandonada(
    contexto_tenant, restaurant, branch, manager_user, comanda, produto,
    sem_caixa_obrigatorio,
):
    """O cartão foi anexado a uma conta que ninguém concluiu."""
    launch_item(command=comanda, product=produto, user=manager_user, quantity=1)
    pedido = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COMMAND,
        user=manager_user,
    )
    attach_commands_to_order(order=pedido, command_ids=[comanda.pk], user=manager_user)
    return pedido


def test_a_recusa_DIZ_que_o_cartao_esta_em_outra_conta(
    conta_abandonada, comanda, restaurant, branch, manager_user
):
    """O defeito que custou o diagnóstico: a mensagem mandava ao lugar errado.

    O cartão tem item pendente — está na tela do operador. Dizer que ele não
    tem manda procurar um consumo que não sumiu; a causa é a conta anterior.
    """
    from django.core.exceptions import ValidationError

    outra = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COMMAND,
        user=manager_user,
    )

    with pytest.raises(ValidationError) as falha:
        attach_commands_to_order(
            order=outra, command_ids=[comanda.pk], user=manager_user
        )

    recado = " ".join(falha.value.messages).lower()
    assert "outra conta" in recado, recado
    assert "não tem item pendente" not in recado


def test_soltar_o_cartao_DEVOLVE_as_anotacoes_a_pendente(
    conta_abandonada, comanda, manager_user
):
    """O desfazer: o consumo volta para o cartão, inteiro."""
    detach_commands_from_order(
        order=conta_abandonada, command_ids=[comanda.pk], user=manager_user
    )

    pendentes = CommandItem.objects.filter(
        command=comanda, command_status=CommandItem.STATUS_PENDENTE
    )
    assert pendentes.count() == 1
    assert not conta_abandonada.items.exists(), (
        "o item do pedido era cópia da anotação e tinha de sumir com ela"
    )


def test_depois_de_soltar_o_cartao_PODE_ser_cobrado_de_novo(
    conta_abandonada, comanda, restaurant, branch, manager_user
):
    """O que o operador quer: tentar de novo e a conta abrir."""
    detach_commands_from_order(
        order=conta_abandonada, command_ids=[comanda.pk], user=manager_user
    )

    nova = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COMMAND,
        user=manager_user,
    )
    criados = attach_commands_to_order(
        order=nova, command_ids=[comanda.pk], user=manager_user
    )

    assert len(criados) == 1
    nova.refresh_from_db()
    assert nova.total > Decimal("0.00")


def test_soltar_NAO_marca_o_consumo_como_perda(
    conta_abandonada, comanda, manager_user
):
    """A diferença que o fechamento do mês enxerga.

    Cancelar a conta abandonada marcaria as anotações como `cancelled` — o
    prato comido viraria prejuízo no relatório. Soltar as devolve a pendente.
    """
    detach_commands_from_order(
        order=conta_abandonada, command_ids=[comanda.pk], user=manager_user
    )

    estados = set(
        CommandItem.objects.filter(command=comanda).values_list(
            "command_status", flat=True
        )
    )
    assert estados == {CommandItem.STATUS_PENDENTE}


def test_cartao_solto_volta_a_estar_EM_USO(
    conta_abandonada, comanda, manager_user
):
    """Ele tem o que cobrar de novo — a grade do salão precisa mostrar isso."""
    from apps.orders.command_billing import command_has_pending_items

    detach_commands_from_order(
        order=conta_abandonada, command_ids=[comanda.pk], user=manager_user
    )

    comanda.refresh_from_db()
    assert command_has_pending_items(comanda.pk)
    assert comanda.status == Command.STATUS_OCCUPIED


def test_pagar_a_conta_que_ficou_aberta_ainda_funciona(
    conta_abandonada, comanda, manager_user, dinheiro
):
    """Soltar é UMA das saídas. A outra é concluir, e ela não pode quebrar."""
    from apps.payments.services import register_payment

    conta_abandonada.refresh_from_db()
    register_payment(
        order=conta_abandonada,
        user=manager_user,
        payment_method_id=dinheiro.id,
        amount=Decimal(str(conta_abandonada.total)),
        idempotency_key=f"teste-{uuid.uuid4()}",
    )

    comanda.refresh_from_db()
    assert comanda.status == Command.STATUS_FREE
    assert comanda.current_table_id is None
