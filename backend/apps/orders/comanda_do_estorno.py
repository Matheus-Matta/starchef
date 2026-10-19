"""Pagamento desfeito: as anotações das comandas voltam a ter o que cobrar.

O pagamento integral marca as anotações como COBRADAS
(`conclude_items_of_order`), e é isso que deixa o cartão livre — "em uso" é
ter anotação pendente (`Command.em_uso`). Excluir esse pagamento devolvia o
pedido a "não pago", mas as anotações seguiam cobradas: a comanda aparecia
livre, a fila da balança automática podia entregá-la a outro cliente, e quem
tentasse cobrá-la caía na conta de quem já tinha ido embora.

A anotação volta a PENDENTE porque a conta dela voltou a estar aberta; o
vínculo com o item do pedido continua, então cobrar de novo é concluir ESTA
conta (o caixa é levado a ela), e não abrir outra.
"""
from apps.orders.models import CommandItem, OrderItem


def reabrir_anotacoes(order):
    """Devolve a PENDENTE as anotações que este pedido tinha cobrado. Quantas."""
    ids = OrderItem.objects.filter(order_id=order.pk).exclude(
        command_item__isnull=True).values_list("command_item_id", flat=True)
    reabertas = 0
    # `save` por anotação, e não `update()`: sem o sinal, a volta não chegava à
    # sincronização nem ao tempo real, e o salão continuava vendo o cartão livre.
    for anotacao in CommandItem.objects.filter(pk__in=list(ids), command_status=CommandItem.STATUS_COBRADO):
        anotacao.command_status = CommandItem.STATUS_PENDENTE
        anotacao.command_closed_at = None
        anotacao.save(update_fields=["command_status", "command_closed_at", "updated_at"])
        reabertas += 1
    return reabertas
