"""Transferência coletiva das comandas e contas de uma mesa."""
from apps.core.lote import atualizar_em_lote, criar_em_lote
from apps.orders.models import Order
from apps.restaurants.models import Command, CommandMovementLog, Table


def transfer_all_commands(*, from_table, to_table, user, commands):
    order_ids = [command.current_order_id for command in commands if command.current_order_id]
    orders = list(
        Order.objects.select_for_update()
        .filter(
            pk__in=order_ids,
            status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT],
        )
        .order_by("pk")
    )
    for order in orders:
        order.table = to_table
        order.updated_by = user
    atualizar_em_lote(Order, orders, ["table", "updated_by", "updated_at"])

    logs = []
    for command in commands:
        command.current_table = to_table
        logs.append(
            CommandMovementLog(
                account=command.account,
                restaurant=command.restaurant,
                branch=command.branch,
                command=command,
                action=CommandMovementLog.ACTION_TRANSFERRED,
                table=to_table,
                from_table=from_table,
                waiter=user,
            )
        )
    atualizar_em_lote(Command, commands, ["current_table", "updated_at"])
    criar_em_lote(CommandMovementLog, logs)

    to_table.status = Table.STATUS_OCCUPIED
    to_table.current_order_id = None
    to_table.save(update_fields=["status", "current_order_id", "updated_at"])

    from apps.orders.services import free_table_if_empty

    free_table_if_empty(from_table)
    return len(commands)
