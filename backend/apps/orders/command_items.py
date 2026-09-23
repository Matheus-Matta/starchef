"""O que a comanda tem — e o que ela já teve.

A comanda é um bloco de notas. Ela não abre pedido: anota o consumo, manda para
a produção, e o cartão fica "em uso" enquanto tiver anotação PENDENTE. Concluir
tudo devolve o cartão para a gaveta.

Nada é apagado, só marcado. É por isso que "quanto a comanda 13 consumiu no dia
20" continua respondível depois de o cartão ter sido entregue a outro cliente —
e é a razão de a consulta do que ela tem AGORA nunca poder ser `command.items`
cru, que devolve o histórico inteiro.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.orders.command_item_launch import launch_item as launch_item
from apps.orders.models import CommandItem


def open_items_of_command(command_id):
    """O que a comanda tem AGORA — as anotações pendentes."""
    return (
        CommandItem.objects.filter(
            command_id=command_id, command_status=CommandItem.STATUS_PENDENTE
        )
        .select_related("product", "table", "batch")
        .prefetch_related("addons__addon")
        .order_by("launched_at")
    )


def history_items_of_command(command_id):
    """O que a comanda JÁ TEVE — sem filtro de estado, para o relatório."""
    return (
        CommandItem.objects.filter(command_id=command_id)
        .select_related("product", "table", "batch")
        .prefetch_related("addons__addon")
        .order_by("-launched_at")
    )


def conclude_item(item, *, when=None, billed=False):
    """Tira UMA anotação da comanda.

    O padrão é CANCELADO porque este caminho é o do item removido ou dado de
    cortesia — ele sai sem ter sido cobrado, e o relatório precisa ver isso
    como perda, não como venda.

    Cancelar na cozinha e sair da comanda são dimensões diferentes, mas um item
    cancelado precisa sair do cartão também: senão ele ocupa a comanda do
    próximo cliente.

    TIRAR A ÚLTIMA ANOTAÇÃO DEVOLVE O CARTÃO PARA A GAVETA — aqui, e não em
    quem chama. "Em uso" é ter o que cobrar; quando a última anotação sai, o
    cartão deixou de estar em uso no mesmo instante, e quem sabe disso é esta
    função. Deixar a liberação a cargo do chamador era o que fazia o cartão
    ficar preso: o caminho do pagamento lembrava de liberar, o do
    cancelamento de item não — e o cartão sumia do salão, ocupado por um
    consumo que já não existia, sem nada estourar em lugar nenhum.
    """
    if item.finalizado:
        return item
    with transaction.atomic():
        item.command_status = (
            CommandItem.STATUS_COBRADO if billed else CommandItem.STATUS_CANCELADO
        )
        item.command_closed_at = when or timezone.now()
        item.save(update_fields=["command_status", "command_closed_at", "updated_at"])
        # `free_command_if_empty` não faz nada quando ainda há o que cobrar,
        # então chamar sempre é mais barato que decidir aqui — e não deixa
        # brecha para o próximo caminho de saída esquecer.
        if item.command_id:
            free_command_if_empty(item.command, user=item.updated_by)
    return item


def free_command_if_empty(command, *, user=None):
    """Devolve o cartão para a gaveta quando não sobrou nada A COBRAR.

    Não é "nada pendente": um item cancelado ou de cortesia continua pendente e
    não soma um centavo. Um cartão só com esses está livre na prática, e
    tratá-lo como ocupado prende a mesa e deixa o operador procurando uma conta
    que não existe.

    Libera também a mesa, se nenhuma outra comanda estiver sentada nela: a
    ocupação do salão é decidida pelas comandas vinculadas, e o pedido guarda a
    mesa só como histórico.
    """
    from apps.orders.command_billing import command_has_pending_items
    from apps.restaurants.models import Command, CommandMovementLog, Table

    if command_has_pending_items(command.pk):
        return False

    # O QUE SOBROU SEM VALOR É ENCERRADO AQUI.
    #
    # Sem isto, o item de cortesia ficaria pendente para sempre num cartão
    # "livre" — e entraria na conta do PRÓXIMO cliente, que pagaria (ou veria)
    # o consumo de quem esteve na mesa antes. É o vazamento que o estado
    # concluído existe para impedir.
    agora = timezone.now()
    CommandItem.objects.filter(
        command_id=command.pk, command_status=CommandItem.STATUS_PENDENTE
    ).update(
        command_status=CommandItem.STATUS_CANCELADO,
        command_closed_at=agora,
        updated_at=agora,
    )

    command = Command.objects.select_for_update().get(pk=command.pk)
    mesa_anterior = command.current_table_id

    # `status` não é gravado: ele se calcula do consumo, que esta função
    # acabou de zerar. O que ainda é estado de verdade do cartão — o nome do
    # cliente, a mesa e o resto do modelo antigo — continua sendo limpo aqui.
    command.customer_name = ""
    command.current_table = None
    # `current_order_id` é resto do modelo antigo, em que a comanda ABRIA
    # pedido. Ele não é mais escrito no fluxo novo, mas um cartão que passou
    # pelo fluxo velho carrega o valor — e deixá-lo aqui faria o cartão livre
    # apontar para o pedido do cliente ANTERIOR.
    command.current_order_id = None
    command.updated_by = user
    command.save(
        update_fields=[
            "customer_name",
            "current_table",
            "current_order_id",
            "updated_by",
            "updated_at",
        ]
    )

    if mesa_anterior:
        CommandMovementLog.objects.create(
            account=command.account,
            restaurant=command.restaurant,
            branch=command.branch,
            command=command,
            action=CommandMovementLog.ACTION_UNLINKED,
            from_table_id=mesa_anterior,
            waiter=user,
        )
        mesa = Table.objects.select_for_update().get(pk=mesa_anterior)
        if not mesa.active_commands.exists():
            mesa.status = Table.STATUS_FREE
            mesa.current_order_id = None
            mesa.save(update_fields=["status", "current_order_id", "updated_at"])
    return True


def assert_command_is_billable(command):
    """Recusa o cartão que não tem nada a cobrar.

    "Em uso" é ter anotação pendente, não um campo de estado. Um cartão livre
    incluído numa conta só produz um pedido preso a um cartão que ninguém está
    usando — e alguém tem de cancelar depois.
    """
    from apps.orders.command_billing import command_has_pending_items

    if not command_has_pending_items(command.pk):
        raise ValidationError(
            f"A comanda {command.number} não tem item pendente: não há nada a cobrar nela."
        )
