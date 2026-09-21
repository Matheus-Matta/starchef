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

from apps.core.tenant import tenant_context
from apps.orders.models import CommandItem


def open_items_of_command(command_id):
    """O que a comanda tem AGORA — as anotações pendentes."""
    return (
        CommandItem.objects.filter(
            command_id=command_id, command_status=CommandItem.STATUS_PENDENTE
        )
        .select_related("product", "table", "batch")
        .order_by("launched_at")
    )


def history_items_of_command(command_id):
    """O que a comanda JÁ TEVE — sem filtro de estado, para o relatório."""
    return (
        CommandItem.objects.filter(command_id=command_id)
        .select_related("product", "table", "batch")
        .order_by("-launched_at")
    )


def launch_item(*, command, product, user, quantity=1, unit_price=None, **extras):
    """Anota um consumo na comanda. Não cria pedido nenhum.

    A mesa vai no item, e não só na comanda: a comanda anda pelo salão, e é
    isto que responde "o que saiu na mesa 4" depois de o cliente ter trocado de
    lugar.
    """
    from apps.menu.models import Product

    if not isinstance(product, Product):
        product = Product.objects.get(pk=product)

    preco = unit_price if unit_price is not None else product.current_price
    with tenant_context(command.account), transaction.atomic():
        item = CommandItem.objects.create(
            account=command.account,
            restaurant=command.restaurant,
            branch=command.branch,
            command=command,
            table=command.current_table,
            product=product,
            quantity=quantity,
            unit_price=preco,
            total_price=preco * quantity,
            production_sector=product.production_sector,
            launched_by=user,
            created_by=user,
            updated_by=user,
            **extras,
        )
        _marcar_em_uso(command, user=user)
    return item


def _marcar_em_uso(command, *, user=None):
    """A comanda passa a estar em uso no primeiro lançamento.

    O estado é DERIVADO de ter anotação pendente — este campo é só o retrato
    que as listas leem sem precisar contar itens de cada cartão.
    """
    from apps.restaurants.models import Command

    if command.status == Command.STATUS_OCCUPIED:
        return
    command.status = Command.STATUS_OCCUPIED
    command.updated_by = user
    command.save(update_fields=["status", "updated_by", "updated_at"])


def conclude_item(item, *, when=None, billed=False):
    """Tira UMA anotação da comanda.

    O padrão é CANCELADO porque este caminho é o do item removido ou dado de
    cortesia — ele sai sem ter sido cobrado, e o relatório precisa ver isso
    como perda, não como venda.

    Cancelar na cozinha e sair da comanda são dimensões diferentes, mas um item
    cancelado precisa sair do cartão também: senão ele ocupa a comanda do
    próximo cliente.
    """
    if item.finalizado:
        return item
    item.command_status = (
        CommandItem.STATUS_COBRADO if billed else CommandItem.STATUS_CANCELADO
    )
    item.command_closed_at = when or timezone.now()
    item.save(update_fields=["command_status", "command_closed_at", "updated_at"])
    return item


def free_command_if_empty(command, *, user=None):
    """Devolve o cartão para a gaveta quando não sobrou nada pendente.

    Libera também a mesa, se nenhuma outra comanda estiver sentada nela: a
    ocupação do salão é decidida pelas comandas vinculadas, e o pedido guarda a
    mesa só como histórico.
    """
    from apps.orders.command_billing import command_has_pending_items
    from apps.restaurants.models import Command, CommandMovementLog, Table

    if command_has_pending_items(command.pk):
        return False

    command = Command.objects.select_for_update().get(pk=command.pk)
    mesa_anterior = command.current_table_id

    command.status = Command.STATUS_FREE
    command.customer_name = ""
    command.current_table = None
    command.updated_by = user
    command.save(
        update_fields=[
            "status",
            "customer_name",
            "current_table",
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
