"""As comandas de onde veio o consumo de um pedido.

Desde que a comanda virou bloco de notas, o pedido nasce NO CAIXA a partir das
anotações dos cartões e `order.command` fica vazio. Quem sabe a origem é cada
item: `OrderItem.command` (lançado direto no cartão) ou
`OrderItem.command_item.command` (anotação copiada para a conta).
"""
from django.db.models import Q


def comandas_do_pedido(order):
    """Comandas do pedido, pela ordem do número. Vazio no balcão/entrega."""
    from apps.restaurants.models import Command

    if order.command_id:
        return [order.command]
    return list(
        Command.all_objects.filter(
            Q(items__order_id=order.pk) | Q(command_items__order_items__order_id=order.pk)
        )
        .distinct()
        .order_by("number")
    )
