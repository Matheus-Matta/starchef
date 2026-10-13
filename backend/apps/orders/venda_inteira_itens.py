"""Os itens da venda inteira, validados em lote (`venda_inteira.py`)."""
from django.core.exceptions import ValidationError

from apps.core import uuid_do_aparelho
from apps.core.lote import criar_em_lote
from apps.orders.models import OrderItem, OrderItemAddon
from apps.orders.venda_inteira_partes import leitura_da_balanca


def lancar_itens(pedido, user, linhas):
    """Os itens da venda, validados EM LOTE.

    Item a item eram ~19 idas ao banco por linha (o item já existe? o
    produto, a disponibilidade, a promoção, o pedido relido e travado de
    novo). Na nuvem, a ~6 ms cada, uma venda de 10 itens levava segundos. Aqui
    as leituras são uma por venda; por item sobra só o que grava.
    """
    from apps.menu.models import Product
    from apps.orders.services import add_order_item, recalculate_order
    from apps.orders.venda_inteira import VendaEmConflito
    from apps.promotions.pricing import primar

    ids = []
    for linha in linhas:
        item_id = uuid_do_aparelho.ler(linha.get("id"), "item")
        if item_id is None:
            raise ValidationError("Cada item precisa do identificador dado pelo PDV.")
        ids.append(item_id)
    if not ids:
        return
    # Reenvio: o item que já existe é reconhecido pelo UUID, e não volta.
    lancados = dict(OrderItem.all_objects.filter(pk__in=ids).values_list("pk", "order_id"))
    if any(dono != pedido.pk for dono in lancados.values()):
        raise VendaEmConflito("Um dos itens já pertence a outro pedido.")
    novos, vistos = [], set(lancados)
    for item_id, linha in zip(ids, linhas, strict=True):
        if item_id not in vistos:
            vistos.add(item_id)
            novos.append((item_id, linha))
    pedidos = {str(linha.get("product")) for _, linha in novos if linha.get("product")}
    produtos = {str(p.pk): p for p in Product.objects.filter(pk__in=pedidos)}
    no_restaurante = {str(pk) for pk in Product.objects.filter(
        pk__in=pedidos, restaurants=pedido.restaurant_id).values_list("pk", flat=True)}
    # A disputa de promoções, uma vez para todos (sem restaurante, como o
    # `current_price` de um produto avulso: o preço não muda por vir em lote).
    primar(list(produtos.values()))
    montados = []
    for item_id, linha in novos:
        produto = produtos.get(str(linha.get("product")))
        if produto is None:
            raise ValidationError("Produto não encontrado.")
        if str(produto.pk) not in no_restaurante:
            raise ValidationError("O produto não está disponível neste restaurante.")
        montados.append(add_order_item(
            order=pedido, product=produto, user=user, item_id=item_id,
            quantity=linha.get("quantity"), variations=linha.get("variations") or [],
            addons=linha.get("addons") or [], customer_note=linha.get("customer_note") or "",
            scale_reading=leitura_da_balanca(pedido, linha.get("scale_reading")),
            weight_kg=linha.get("weight_kg"), expected_unit_price=linha.get("expected_unit_price"),
            metafields=linha.get("metafields"), recalcular=False, lote=True,
        ))
    # Todos de uma vez (`core/lote.py`): eram uma gravação por item e outra
    # por adicional, cada uma com a sua captura.
    criar_em_lote(OrderItem, montados)
    criar_em_lote(OrderItemAddon, [a for item in montados for a in item._lote_adicionais])
    for item in montados:
        if item._lote_leitura is not None:
            item._lote_leitura.order_item = item
            item._lote_leitura.save(update_fields=["order_item", "updated_at"])
    # O total é projeção dos itens: uma vez no fim, e não uma por item.
    if novos:
        recalculate_order(pedido)
