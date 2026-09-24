"""O cenario que as duas regras de cancelamento compartilham.

Um item de pedido que JA chegou a producao ha um tempo dado. Fica aqui, e nao
duplicado nos dois arquivos, porque o dia em que o "chegou a producao" mudar
de forma os dois precisam mudar juntos.
"""
from datetime import timedelta

from django.utils import timezone

from apps.orders.models import Order, OrderItem
from apps.orders.services import add_order_item, create_order


def item_na_producao(restaurant, branch, produto, user, *, ha_segundos):
    """Um item de pedido que chegou a producao ha `ha_segundos`."""
    pedido = create_order(
        restaurant=restaurant, branch=branch,
        order_type=Order.TYPE_COUNTER, user=user,
    )
    item = add_order_item(order=pedido, product=produto, quantity=1, user=user)
    # `all_objects`, e nao `objects`: o manager padrao e escopado por conta e o
    # teste roda fora do ciclo da requisicao, sem conta no ar. Com `objects` o
    # queryset vem VAZIO e o `update` nao pega nada — em silencio, porque
    # `update` devolve 0 e ninguem olha.
    OrderItem.all_objects.filter(pk=item.pk).update(
        status=OrderItem.STATUS_SENT,
        sent_to_kitchen_at=timezone.now() - timedelta(seconds=ha_segundos),
    )
    item.refresh_from_db()
    return item
