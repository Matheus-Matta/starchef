from apps.orders.models import OrderItem, OrderItemAddon


def to_order_item(annotation, *, order, user):
    """Copia preço e produção do consumo, sem reler o cadastro atual."""
    return OrderItem(
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
        launched_by=annotation.launched_by,
        created_by=user,
        updated_by=user,
    )


def copy_addons(annotations, items, *, order, user):
    """Mantém no pedido os adicionais escolhidos enquanto estavam na comanda."""
    OrderItemAddon.objects.bulk_create(
        [
            OrderItemAddon(
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
    )
