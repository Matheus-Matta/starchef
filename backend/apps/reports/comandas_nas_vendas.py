"""Quantas comandas os pedidos pagos do período pagaram, e o ticket de cada uma.

Um pedido pode pagar várias comandas (conta agrupada), então pedido e comanda
são contagens diferentes: 100 pedidos podem ser 150 comandas. A comanda de um
pedido vem do ITEM (`OrderItem.command`, que nasce com o item e nunca muda) e,
no pedido antigo sem item marcado, do próprio `Order.command`.

O ticket divide só o valor dos pedidos que tiveram comanda: a venda do balcão
no numerador inflaria o ticket por comanda.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q, Sum


def resumo(pedidos_pagos):
    from apps.orders.models import Order, OrderItem

    ids_pagos = pedidos_pagos.values("pk")
    pares_por_item = (
        OrderItem.objects.filter(order_id__in=ids_pagos, command__isnull=False)
        .values("order_id", "command_id")
        .distinct()
        .count()
    )
    com_item_marcado = OrderItem.objects.filter(order_id__in=ids_pagos, command__isnull=False).values("order_id")
    # Pedido legado: a comanda só está no cabeçalho. Quem tem item marcado já
    # foi contado acima, e contá-lo de novo duplicaria o cartão.
    so_no_cabecalho = (
        Order.objects.filter(pk__in=ids_pagos, command__isnull=False).exclude(pk__in=com_item_marcado).count()
    )
    quantidade = pares_por_item + so_no_cabecalho

    total = Order.objects.filter(
        Q(pk__in=com_item_marcado) | Q(command__isnull=False), pk__in=ids_pagos
    ).aggregate(valor=Sum("total"))["valor"] or Decimal("0.00")
    ticket = (total / quantidade).quantize(Decimal("0.01"), ROUND_HALF_UP) if quantidade else Decimal("0.00")
    return {
        "commands_count": quantidade,
        "commands_total": total,
        "commands_average_ticket": ticket,
    }
