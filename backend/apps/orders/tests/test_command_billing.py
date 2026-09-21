"""A comanda como bloco de notas, e a conta que cobra várias delas.

O desenho que estes testes fixam:

* a comanda **não cria pedido** — ela anota;
* "em uso" é ter anotação PENDENTE, não um campo de estado;
* o pedido do caixa **puxa** as anotações pendentes e guarda o fio de volta;
* encerrar o pedido conclui as anotações e devolve os cartões para a gaveta;
* o que foi concluído **não entra na conta de outro cliente**;
* e nada disso desanda com uma mesa de duzentos cartões.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.core.tenant import tenant_context
from apps.orders.command_billing import (
    attach_commands_to_order,
    command_has_pending_items,
    conclude_items_of_order,
    detach_commands_from_order,
)
from apps.orders.command_items import free_command_if_empty, launch_item, open_items_of_command
from apps.orders.models import CommandItem, Order, OrderItem
from apps.restaurants.models import Command


def _comanda(restaurant, branch, numero):
    return Command.objects.create(
        account=restaurant.account,
        restaurant=restaurant,
        branch=branch,
        number=numero,
        code=f"CMD-{numero:04d}",
    )


def _pedido(restaurant, branch, user):
    """Pelo serviço, e não por `objects.create`: é ele que numera o pedido."""
    from apps.orders.services import create_order

    return create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=user,
    )


@pytest.mark.django_db
def test_lancar_na_comanda_nao_cria_pedido(restaurant, branch, manager_user, produto):
    """O gesto que prendia o cartão: abrir pedido para anotar um refrigerante."""
    comanda = _comanda(restaurant, branch, 1)

    launch_item(command=comanda, product=produto, user=manager_user, quantity=2)

    with tenant_context(restaurant.account):
        assert Order.objects.count() == 0
        assert CommandItem.objects.filter(command=comanda).count() == 1
        comanda.refresh_from_db()
        assert comanda.status == Command.STATUS_OCCUPIED


@pytest.mark.django_db
def test_em_uso_e_ter_anotacao_pendente(restaurant, branch, manager_user, produto):
    comanda = _comanda(restaurant, branch, 2)
    assert command_has_pending_items(comanda.pk) is False

    launch_item(command=comanda, product=produto, user=manager_user)

    assert command_has_pending_items(comanda.pk) is True


@pytest.mark.django_db
def test_a_conta_puxa_as_anotacoes_e_guarda_o_fio(
    restaurant, branch, manager_user, produto
):
    comanda = _comanda(restaurant, branch, 3)
    anotacao = launch_item(command=comanda, product=produto, user=manager_user, quantity=2)
    pedido = _pedido(restaurant, branch, manager_user)

    criados = attach_commands_to_order(
        order=pedido, command_ids=[comanda.pk], user=manager_user
    )

    assert len(criados) == 1
    item = criados[0]
    assert item.command_item_id == anotacao.pk
    assert item.command_id == comanda.pk
    # O preço vem da ANOTAÇÃO, não do cadastro: o cliente consumiu ao preço do
    # momento do lançamento.
    assert item.unit_price == anotacao.unit_price


@pytest.mark.django_db
def test_cartao_sem_nada_pendente_e_recusado(restaurant, branch, manager_user):
    """Cartão livre não tem o que cobrar — e não pode prender um pedido."""
    comanda = _comanda(restaurant, branch, 4)
    pedido = _pedido(restaurant, branch, manager_user)

    with pytest.raises(ValidationError):
        attach_commands_to_order(
            order=pedido, command_ids=[comanda.pk], user=manager_user
        )


@pytest.mark.django_db
def test_incluir_o_mesmo_cartao_duas_vezes_nao_cobra_em_dobro(
    restaurant, branch, manager_user, produto
):
    """O leitor dispara duas leituras com frequência."""
    comanda = _comanda(restaurant, branch, 5)
    launch_item(command=comanda, product=produto, user=manager_user)
    pedido = _pedido(restaurant, branch, manager_user)

    attach_commands_to_order(order=pedido, command_ids=[comanda.pk], user=manager_user)
    with pytest.raises(ValidationError):
        attach_commands_to_order(
            order=pedido, command_ids=[comanda.pk], user=manager_user
        )

    with tenant_context(restaurant.account):
        assert OrderItem.objects.filter(order=pedido).count() == 1


@pytest.mark.django_db
def test_encerrar_o_pedido_conclui_as_anotacoes_e_libera_o_cartao(
    restaurant, branch, manager_user, produto
):
    comanda = _comanda(restaurant, branch, 6)
    launch_item(command=comanda, product=produto, user=manager_user)
    pedido = _pedido(restaurant, branch, manager_user)
    attach_commands_to_order(order=pedido, command_ids=[comanda.pk], user=manager_user)

    conclude_items_of_order(pedido, billed=True)
    with tenant_context(restaurant.account):
        free_command_if_empty(comanda, user=manager_user)

    assert list(open_items_of_command(comanda.pk)) == []
    comanda.refresh_from_db()
    assert comanda.status == Command.STATUS_FREE
    # Nada foi apagado: o histórico é o que responde "o que a 6 consumiu hoje".
    with tenant_context(restaurant.account):
        assert CommandItem.objects.filter(command=comanda).count() == 1


@pytest.mark.django_db
def test_o_concluido_nao_entra_na_conta_do_proximo_cliente(
    restaurant, branch, manager_user, produto
):
    """O cartão volta para a gaveta e é entregue a outra pessoa."""
    comanda = _comanda(restaurant, branch, 7)
    launch_item(command=comanda, product=produto, user=manager_user)
    primeiro = _pedido(restaurant, branch, manager_user)
    attach_commands_to_order(order=primeiro, command_ids=[comanda.pk], user=manager_user)
    conclude_items_of_order(primeiro, billed=True)

    # Cliente novo, mesmo cartão.
    nova = launch_item(command=comanda, product=produto, user=manager_user)
    segundo = _pedido(restaurant, branch, manager_user)
    criados = attach_commands_to_order(
        order=segundo, command_ids=[comanda.pk], user=manager_user
    )

    assert [item.command_item_id for item in criados] == [nova.pk]


@pytest.mark.django_db
def test_duzentas_comandas_numa_conta_so(restaurant, branch, manager_user, produto):
    """O requisito que motivou o desenho inteiro.

    No modelo antigo isto seriam duzentos pedidos, uma consolidação e um laço
    movendo item por item. Aqui é uma leitura e um `bulk_create` — o custo
    cresce com a quantidade de ITENS, não com a de comandas.
    """
    comandas = [_comanda(restaurant, branch, 1000 + i) for i in range(200)]
    for comanda in comandas:
        launch_item(command=comanda, product=produto, user=manager_user)
    pedido = _pedido(restaurant, branch, manager_user)

    criados = attach_commands_to_order(
        order=pedido, command_ids=[c.pk for c in comandas], user=manager_user
    )

    assert len(criados) == 200
    with tenant_context(restaurant.account):
        assert OrderItem.objects.filter(order=pedido).count() == 200
        # Nenhum pedido nasceu por comanda.
        assert Order.objects.count() == 1

    conclude_items_of_order(pedido, billed=True)
    with tenant_context(restaurant.account):
        assert (
            CommandItem.objects.filter(
                command_id__in=[c.pk for c in comandas],
                command_status=CommandItem.STATUS_PENDENTE,
            ).count()
            == 0
        )


@pytest.mark.django_db
def test_o_total_pendente_ignora_cancelado_e_cortesia(
    restaurant, branch, manager_user, produto
):
    from apps.orders.command_billing import total_pendente

    comanda = _comanda(restaurant, branch, 8)
    launch_item(command=comanda, product=produto, user=manager_user, unit_price=Decimal("10.00"))
    cortesia = launch_item(
        command=comanda, product=produto, user=manager_user, unit_price=Decimal("7.00")
    )
    cortesia.status = CommandItem.STATUS_COMPED
    cortesia.save(update_fields=["status"])

    assert total_pendente(comanda.pk) == Decimal("10.00")


@pytest.mark.django_db
def test_cobrado_e_cancelado_sao_estados_DIFERENTES(
    restaurant, branch, manager_user, produto
):
    """Venda e perda não podem virar a mesma linha no fechamento do mês.

    Um estado só para "saiu da comanda" obrigaria o relatório a adivinhar a
    diferença olhando o pedido — que pode nem existir mais.
    """
    vendida = _comanda(restaurant, branch, 20)
    perdida = _comanda(restaurant, branch, 21)
    launch_item(command=vendida, product=produto, user=manager_user)
    launch_item(command=perdida, product=produto, user=manager_user)

    paga = _pedido(restaurant, branch, manager_user)
    attach_commands_to_order(order=paga, command_ids=[vendida.pk], user=manager_user)
    conclude_items_of_order(paga, billed=True)

    cancelada = _pedido(restaurant, branch, manager_user)
    attach_commands_to_order(order=cancelada, command_ids=[perdida.pk], user=manager_user)
    conclude_items_of_order(cancelada, billed=False)

    with tenant_context(restaurant.account):
        assert (
            CommandItem.objects.get(command=vendida).command_status
            == CommandItem.STATUS_COBRADO
        )
        assert (
            CommandItem.objects.get(command=perdida).command_status
            == CommandItem.STATUS_CANCELADO
        )
    # Nenhum dos dois volta para a conta de outro cliente.
    assert list(open_items_of_command(vendida.pk)) == []
    assert list(open_items_of_command(perdida.pk)) == []


@pytest.mark.django_db
def test_tirar_a_comanda_da_conta_sem_cancelar_nada(
    restaurant, branch, manager_user, produto
):
    """O desfazer do caixa: incluiu o cartão errado.

    A anotação volta a PENDENTE e o cartão volta a ter o que cobrar. Cancelar
    a conta inteira para corrigir uma inclusão seria caro demais para um
    engano de um toque.
    """
    comanda = _comanda(restaurant, branch, 22)
    anotacao = launch_item(command=comanda, product=produto, user=manager_user)
    pedido = _pedido(restaurant, branch, manager_user)
    attach_commands_to_order(order=pedido, command_ids=[comanda.pk], user=manager_user)

    resumo = detach_commands_from_order(
        order=pedido, command_ids=[comanda.pk], user=manager_user
    )

    assert resumo["itens"] == 1
    with tenant_context(restaurant.account):
        assert OrderItem.objects.filter(order=pedido).count() == 0
    anotacao.refresh_from_db()
    assert anotacao.command_status == CommandItem.STATUS_PENDENTE
    assert command_has_pending_items(comanda.pk) is True
    comanda.refresh_from_db()
    assert comanda.status == Command.STATUS_OCCUPIED


@pytest.mark.django_db
def test_removida_a_comanda_ela_pode_entrar_em_outra_conta(
    restaurant, branch, manager_user, produto
):
    """O caso real: o cliente resolveu pagar separado."""
    comanda = _comanda(restaurant, branch, 23)
    launch_item(command=comanda, product=produto, user=manager_user)
    errada = _pedido(restaurant, branch, manager_user)
    attach_commands_to_order(order=errada, command_ids=[comanda.pk], user=manager_user)
    detach_commands_from_order(order=errada, command_ids=[comanda.pk], user=manager_user)

    certa = _pedido(restaurant, branch, manager_user)
    criados = attach_commands_to_order(
        order=certa, command_ids=[comanda.pk], user=manager_user
    )

    assert len(criados) == 1


@pytest.mark.django_db
def test_pedido_encerrado_nao_solta_mais_comanda(
    restaurant, branch, manager_user, produto
):
    """Depois de pago, as anotações já têm destino: mexer reescreveria o histórico."""
    comanda = _comanda(restaurant, branch, 24)
    launch_item(command=comanda, product=produto, user=manager_user)
    pedido = _pedido(restaurant, branch, manager_user)
    attach_commands_to_order(order=pedido, command_ids=[comanda.pk], user=manager_user)
    pedido.status = Order.STATUS_PAID
    pedido.save(update_fields=["status"])

    with pytest.raises(ValidationError):
        detach_commands_from_order(
            order=pedido, command_ids=[comanda.pk], user=manager_user
        )


@pytest.mark.django_db
def test_cartao_so_com_cortesia_esta_LIVRE(restaurant, branch, manager_user, produto):
    """Pendente não basta: o que decide é ter o que COBRAR.

    Um cartão cujos pendentes são todos cortesia não tem conta nenhuma.
    Tratá-lo como ocupado prende a mesa e manda o operador procurar uma conta
    que não existe.
    """
    comanda = _comanda(restaurant, branch, 30)
    cortesia = launch_item(command=comanda, product=produto, user=manager_user)
    cortesia.status = CommandItem.STATUS_COMPED
    cortesia.save(update_fields=["status"])

    assert command_has_pending_items(comanda.pk) is False


@pytest.mark.django_db
def test_cartao_sem_valor_nao_entra_numa_conta(restaurant, branch, manager_user, produto):
    comanda = _comanda(restaurant, branch, 31)
    cancelado = launch_item(command=comanda, product=produto, user=manager_user)
    cancelado.status = CommandItem.STATUS_CANCELLED
    cancelado.save(update_fields=["status"])
    pedido = _pedido(restaurant, branch, manager_user)

    with pytest.raises(ValidationError):
        attach_commands_to_order(
            order=pedido, command_ids=[comanda.pk], user=manager_user
        )


@pytest.mark.django_db
def test_liberar_o_cartao_ENCERRA_o_que_sobrou_sem_valor(
    restaurant, branch, manager_user, produto
):
    """O vazamento que o estado concluído existe para impedir.

    Sem isto, a cortesia ficaria pendente para sempre num cartão "livre" — e
    entraria na conta do PRÓXIMO cliente, que veria o consumo de quem esteve
    na mesa antes.
    """
    comanda = _comanda(restaurant, branch, 32)
    cobravel = launch_item(command=comanda, product=produto, user=manager_user)
    cortesia = launch_item(command=comanda, product=produto, user=manager_user)
    cortesia.status = CommandItem.STATUS_COMPED
    cortesia.save(update_fields=["status"])

    pedido = _pedido(restaurant, branch, manager_user)
    criados = attach_commands_to_order(
        order=pedido, command_ids=[comanda.pk], user=manager_user
    )
    # Só o que tem valor foi para a conta.
    assert [item.command_item_id for item in criados] == [cobravel.pk]

    conclude_items_of_order(pedido, billed=True)
    with tenant_context(restaurant.account):
        free_command_if_empty(comanda, user=manager_user)

    comanda.refresh_from_db()
    assert comanda.status == Command.STATUS_FREE
    # A cortesia NÃO ficou pendente para o próximo cliente.
    cortesia.refresh_from_db()
    assert cortesia.command_status == CommandItem.STATUS_CANCELADO
    assert list(open_items_of_command(comanda.pk)) == []


@pytest.mark.django_db
def test_o_proximo_cliente_nao_herda_nada(restaurant, branch, manager_user, produto):
    """O cartão volta para a gaveta e é entregue a outra pessoa."""
    comanda = _comanda(restaurant, branch, 33)
    cortesia = launch_item(command=comanda, product=produto, user=manager_user)
    cortesia.status = CommandItem.STATUS_COMPED
    cortesia.save(update_fields=["status"])

    with tenant_context(restaurant.account):
        free_command_if_empty(comanda, user=manager_user)

    # Cliente novo, mesmo cartão.
    nova = launch_item(command=comanda, product=produto, user=manager_user)
    pedido = _pedido(restaurant, branch, manager_user)
    criados = attach_commands_to_order(
        order=pedido, command_ids=[comanda.pk], user=manager_user
    )

    assert [item.command_item_id for item in criados] == [nova.pk]

