import uuid

from apps.orders.models import OrderItem, OrderItemAddon

# O UUID do item que nasce de uma anotação é CALCULADO, não sorteado: a mesma
# venda (mesmo pedido, mesma anotação) feita na loja e na nuvem — o PDV que
# reenviou depois de uma troca de servidor — gera o MESMO item nos dois, e a
# sincronização os junta pelo id em vez de somar dois.
_ESPACO = uuid.UUID("6f7c1b4e-2d0a-4c55-9a3e-5b1d2c3e4f60")


def id_do_item_da_anotacao(order_id, annotation_id):
    return uuid.uuid5(_ESPACO, f"{order_id}:{annotation_id}")


def copy_items_to_order(annotations, *, order, user):
    """Copia itens e adicionais, registrando os eventos na transação atual."""
    novos = [to_order_item(annotation, order=order, user=user) for annotation in annotations]
    # O UUID calculado já ocupado por uma linha que ficou para trás (excluída
    # sem ser apagada) derrubaria o lote inteiro. Esse item ganha um sorteado:
    # perde só a junção automática entre loja e nuvem, que ali não se aplica.
    ocupados = set(OrderItem.all_objects.filter(pk__in=[i.pk for i in novos])
                   .values_list("pk", flat=True))
    for item in novos:
        if item.pk in ocupados:
            item.pk = uuid.uuid4()
    items = OrderItem.objects.bulk_create(novos)

    # `bulk_create` pula `post_save`; sem a outbox explícita, a nuvem recebe o
    # pedido sem as linhas que formam o total. Tudo permanece na transação da cobrança.
    from apps.synchronization.services import outbox

    for item in items:
        outbox.record(item)

    addons = copy_addons(annotations, items, order=order, user=user)
    for addon in addons:
        outbox.record(addon)
    return items


def to_order_item(annotation, *, order, user):
    """Copia preço e produção do consumo, sem reler o cadastro atual."""
    return OrderItem(
        id=id_do_item_da_anotacao(order.pk, annotation.pk),
        account=order.account,
        restaurant=order.restaurant,
        branch=order.branch,
        order=order,
        command_id=annotation.command_id,
        command_item=annotation,
        product_id=annotation.product_id,
        quantity=annotation.quantity,
        unit_price=annotation.unit_price,
        total_price=annotation.total_price,
        variations=annotation.variations,
        customer_note=annotation.customer_note,
        production_sector=annotation.production_sector,
        status=annotation.status,
        sent_to_kitchen_at=annotation.sent_to_kitchen_at,
        preparation_started_at=annotation.preparation_started_at,
        ready_at=annotation.ready_at,
        delivered_at=annotation.delivered_at,
        # O código foi digitado no atendimento da comanda. Copiá-lo é o que
        # mantém a autoria do garçom quando o caixa transforma a anotação em venda.
        metafields=annotation.metafields,
        launched_by=annotation.launched_by,
        created_by=user,
        updated_by=user,
    )


def copy_addons(annotations, items, *, order, user):
    """Mantém no pedido os adicionais escolhidos enquanto estavam na comanda."""
    adicionais = [
        OrderItemAddon(
            id=uuid.uuid5(_ESPACO, f"{item.pk}:{addon.pk}"),
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            item=item,
            addon_id=addon.addon_id,
            quantity=addon.quantity,
            unit_price=addon.unit_price,
            total_price=addon.total_price,
            created_by=user,
            updated_by=user,
        )
        for annotation, item in zip(annotations, items, strict=True)
        for addon in annotation.addons.all()
    ]
    return OrderItemAddon.objects.bulk_create(adicionais)
