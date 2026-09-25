from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from apps.core.tenant import tenant_context
from apps.orders.command_item_configuration import configured_values
from apps.orders.models import CommandItem, CommandItemAddon


def launch_item(
    *,
    command,
    product,
    user,
    quantity=1,
    unit_price=None,
    variations=None,
    addons=None,
    customer_note="",
    metafields=None,
):
    """Anota um consumo na comanda sem criar pedido.

    `metafields` carrega o código de QUEM anotou quando o restaurante exige. O
    item herda o que a comanda tiver: quem abriu o cartão já se identificou, e
    exigir o código de novo a cada prato faria o garçom digitar dez vezes no
    mesmo atendimento.
    """
    from apps.menu.models import Product

    from apps.core.metafields import herdar
    from apps.orders.operator_code import exigir

    extras = exigir(
        command.restaurant,
        herdar(metafields, command.metafields),
        acao="lançar item na comanda",
    )

    if not isinstance(product, Product):
        product = Product.objects.get(pk=product)
    quantidade, preco, total, variacoes, adicionais = configured_values(
        product=product,
        quantity=quantity,
        variations=variations,
        addons=addons,
        base_price=unit_price,
    )
    with tenant_context(command.account), transaction.atomic():
        item = CommandItem.objects.create(
            account=command.account,
            restaurant=command.restaurant,
            branch=command.branch,
            command=command,
            table=command.current_table,
            product=product,
            quantity=quantidade,
            unit_price=preco,
            total_price=total,
            variations=variacoes,
            customer_note=customer_note,
            production_sector=product.production_sector,
            launched_by=user,
            created_by=user,
            updated_by=user,
            metafields=extras,
        )
        _create_addons(item, adicionais, quantidade, user)
        _mark_occupied(command, user)
    return item


def _create_addons(item, addons, quantity, user):
    CommandItemAddon.objects.bulk_create(
        [
            CommandItemAddon(
                account=item.account,
                restaurant=item.restaurant,
                branch=item.branch,
                item=item,
                addon=addon,
                quantity=1,
                unit_price=addon.price,
                total_price=(addon.price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                created_by=user,
                updated_by=user,
            )
            for addon in addons
        ]
    )


def _mark_occupied(command, user):
    """Registra quem mexeu no cartão. O "ocupado" não se grava mais.

    Lançar uma anotação JÁ é ocupar o cartão: `Command.status` responde pelo
    consumo pendente. O que ainda vale escrever aqui é a autoria — quem foi o
    último a mexer neste cartão é pergunta de auditoria, não de estado.
    """
    if command.updated_by_id == getattr(user, "pk", None):
        return
    command.updated_by = user
    command.save(update_fields=["updated_by", "updated_at"])
