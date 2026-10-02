"""Produto vendido por peso não entra na produção.

O prato da balança JÁ está servido: o cliente montou e pesou. Mandá-lo ao KDS
punha na tela da cozinha um card que ninguém prepara — e, como o status de
produção do pedido é calculado sobre TODOS os itens, esse card "enviado" para
sempre impedia o pedido de chegar a "pronto". O KDS mostra só produto por
unidade.

Por isso o item por peso sai do envio já ENTREGUE. `sent_to_kitchen_at` é
gravado do mesmo jeito: o prato saiu, e cancelá-lo depois continua exigindo a
autorização de quem cancela o que já chegou ao cliente.
"""


def e_por_peso(item):
    produto = getattr(item, "product", None)
    return bool(produto is not None and produto.is_weighed)


def separar(itens):
    """(por_peso, de_producao) — na mesma ordem em que chegaram."""
    por_peso = [item for item in itens if e_por_peso(item)]
    return por_peso, [item for item in itens if not e_por_peso(item)]


def entregar_sem_producao(itens, *, agora):
    """Marca os itens por peso como entregues, um `save` por item.

    `save`, e não `QuerySet.update()`: sem sinal a mudança não chegaria à
    sincronização nem ao tempo real, e o outro lado veria o prato "enviado".
    """
    for item in itens:
        item.status = item.STATUS_DELIVERED
        item.sent_to_kitchen_at = item.sent_to_kitchen_at or agora
        item.ready_at = item.ready_at or agora
        item.delivered_at = item.delivered_at or agora
        item.save(update_fields=["status", "sent_to_kitchen_at", "ready_at", "delivered_at", "updated_at"])
