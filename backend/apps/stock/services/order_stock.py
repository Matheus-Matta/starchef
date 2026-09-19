"""Motor de consumo de estoque a partir de um pedido.

Tres coisas consomem insumo numa venda, e o motor precisa das tres:

1. a ficha tecnica do produto (`Recipe`), rateada pelo rendimento;
2. os adicionais escolhidos no PDV (`OrderItemAddon`);
3. o produto vendido direto da prateleira, sem ficha (`Product.stock_ingredient`).

Cada componente vira UMA linha de movimento com uma `source_key` propria. E
essa chave que torna a baixa idempotente: `deduct_order_stock` e chamada tanto
no envio para a cozinha (uma vez por lote enviado!) quanto no fechamento do
pagamento, e antes disso cada chamada percorria o pedido inteiro de novo,
baixando tudo outra vez.
"""
from decimal import Decimal

from django.db import transaction

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.menu.units import IncompatibleUnitError, convert
from apps.stock.models import StockLocation, StockMovement

QUANTITY_PLACES = Decimal("0.001")
MONEY_PLACES = Decimal("0.01")

#: Evento que originou a baixa — entra na `source_key`.
EVENT_SALE = "sale"


class StockComponent:
    """Um consumo ja resolvido: qual insumo, quanto, e de onde veio.

    Existe para que receita, adicional e produto direto cheguem no mesmo
    formato na hora de gravar — sem isso, cada origem repetiria a conversao de
    unidade e o calculo de custo, que e onde os tres discordavam entre si.
    """

    __slots__ = ("ingredient", "order_item", "quantity", "unit_cost", "source_key", "snapshot")

    def __init__(self, *, ingredient, order_item, quantity, unit_cost, source_key, snapshot):
        self.ingredient = ingredient
        self.order_item = order_item
        self.quantity = quantity
        self.unit_cost = unit_cost
        self.source_key = source_key
        self.snapshot = snapshot


def _default_location(order, user):
    location, _ = StockLocation.objects.get_or_create(
        restaurant=order.restaurant,
        branch=order.branch,
        name="Principal",
        defaults={
            "account": order.account,
            "created_by": user,
            "updated_by": user,
        },
    )
    return location


def _converted(quantity, from_unit, to_unit):
    """`quantity` na unidade do insumo, ou `None` se as unidades nao conversam.

    Uma linha incoerente (litro de um insumo em grama) e pulada em vez de
    derrubar a venda inteira: o pedido ja foi pago, e travar o fechamento por
    um cadastro torto deixaria o operador sem saida no balcao. O que ficou de
    fora aparece no retorno da funcao, para quem chamou registrar.
    """
    try:
        return convert(quantity, from_unit, to_unit)
    except IncompatibleUnitError:
        return None


def _recipe_components(item, skipped):
    """Consumo da ficha tecnica, ja rateado pelo rendimento da receita."""
    recipe = getattr(item.product, "recipe", None)
    if not recipe or not recipe.auto_deduct_stock or not recipe.is_active:
        return

    # O rendimento e o que faltava: uma receita que rende 10 porcoes e usa
    # 1.000 g de macarrao gasta 100 g por porcao, nao 1.000. Sem dividir, cada
    # venda baixava a producao inteira.
    yield_quantity = Decimal(str(recipe.yield_quantity or 1))
    if yield_quantity <= 0:
        yield_quantity = Decimal("1")

    for recipe_item in recipe.items.all():
        ingredient = recipe_item.ingredient
        per_yield = Decimal(str(recipe_item.quantity))
        declared_unit = recipe_item.unit or ingredient.unit
        quantity = _converted(per_yield, declared_unit, ingredient.unit)
        if quantity is None:
            skipped.append(
                {
                    "reason": "incompatible_unit",
                    "component": "recipe_item",
                    "ingredient": str(ingredient.id),
                    "from_unit": declared_unit,
                    "to_unit": ingredient.unit,
                }
            )
            continue

        total = quantity / yield_quantity * Decimal(str(item.quantity))
        yield StockComponent(
            ingredient=ingredient,
            order_item=item,
            quantity=total,
            unit_cost=recipe_item.ingredient_cost or ingredient.average_cost,
            source_key=f"{EVENT_SALE}:{item.id}:recipe_item:{recipe_item.id}",
            snapshot={
                "component": "recipe_item",
                "recipe": str(recipe.id),
                "recipe_item": str(recipe_item.id),
                "ingredient": str(ingredient.id),
                "quantity_per_yield": str(per_yield),
                "declared_unit": declared_unit,
                "ingredient_unit": ingredient.unit,
                "yield_quantity": str(yield_quantity),
                "item_quantity": str(item.quantity),
            },
        )


def _addon_components(item, skipped):
    """Consumo dos adicionais escolhidos — antes, nao saiam do estoque."""
    for order_addon in item.addons.all():
        addon = order_addon.addon
        ingredient = addon.ingredient
        per_unit = Decimal(str(addon.consumption_quantity or 0))
        if not ingredient or per_unit <= 0:
            continue

        declared_unit = addon.consumption_unit or ingredient.unit
        quantity = _converted(per_unit, declared_unit, ingredient.unit)
        if quantity is None:
            skipped.append(
                {
                    "reason": "incompatible_unit",
                    "component": "addon",
                    "ingredient": str(ingredient.id),
                    "from_unit": declared_unit,
                    "to_unit": ingredient.unit,
                }
            )
            continue

        # A quantidade do adicional ja e por unidade do item; multiplica pelas
        # duas para "2 x-burger com bacon duplo" sair certo.
        total = quantity * Decimal(str(order_addon.quantity or 1)) * Decimal(str(item.quantity))
        yield StockComponent(
            ingredient=ingredient,
            order_item=item,
            quantity=total,
            unit_cost=ingredient.average_cost,
            source_key=f"{EVENT_SALE}:{item.id}:addon:{order_addon.id}",
            snapshot={
                "component": "addon",
                "addon": str(addon.id),
                "order_item_addon": str(order_addon.id),
                "ingredient": str(ingredient.id),
                "quantity_per_unit": str(per_unit),
                "declared_unit": declared_unit,
                "ingredient_unit": ingredient.unit,
                "addon_quantity": str(order_addon.quantity),
                "item_quantity": str(item.quantity),
            },
        )


def _direct_components(item, skipped):
    """Consumo do produto vendido direto, sem ficha tecnica."""
    product = item.product
    ingredient = product.stock_ingredient
    per_unit = Decimal(str(product.stock_consumption_quantity or 0))
    if not ingredient or per_unit <= 0:
        return

    # Um produto com ficha tecnica E vinculo direto baixaria o mesmo saldo
    # duas vezes. A ficha manda, porque descreve a composicao real.
    recipe = getattr(product, "recipe", None)
    if recipe and recipe.auto_deduct_stock and recipe.is_active:
        return

    declared_unit = product.stock_consumption_unit or ingredient.unit
    quantity = _converted(per_unit, declared_unit, ingredient.unit)
    if quantity is None:
        skipped.append(
            {
                "reason": "incompatible_unit",
                "component": "product",
                "ingredient": str(ingredient.id),
                "from_unit": declared_unit,
                "to_unit": ingredient.unit,
            }
        )
        return

    total = quantity * Decimal(str(item.quantity))
    yield StockComponent(
        ingredient=ingredient,
        order_item=item,
        quantity=total,
        unit_cost=ingredient.average_cost,
        source_key=f"{EVENT_SALE}:{item.id}:product:{product.id}",
        snapshot={
            "component": "product",
            "product": str(product.id),
            "ingredient": str(ingredient.id),
            "quantity_per_unit": str(per_unit),
            "declared_unit": declared_unit,
            "ingredient_unit": ingredient.unit,
            "item_quantity": str(item.quantity),
        },
    )


def order_stock_components(order, *, skipped=None):
    """Todo o consumo do pedido, componente a componente.

    Exposta para que a tela consiga pre-visualizar a baixa sem grava-la.
    """
    skipped = skipped if skipped is not None else []
    items = order.items.select_related(
        "product", "product__stock_ingredient"
    ).prefetch_related(
        "product__recipe__items__ingredient",
        "addons__addon__ingredient",
    )
    for item in items:
        # Item cancelado ou cortesia nao chega a sair da cozinha como venda;
        # cortesia continua consumindo (o prato foi feito), cancelado nao.
        if getattr(item, "status", None) == "cancelled":
            continue
        yield from _recipe_components(item, skipped)
        yield from _addon_components(item, skipped)
        yield from _direct_components(item, skipped)


@transaction.atomic
def deduct_order_stock(*, order, user):
    """Baixa o estoque consumido pelo pedido. Chamar de novo nao duplica nada."""
    with tenant_context(order.account):
        location = _default_location(order, user)
        skipped = []
        components = list(order_stock_components(order, skipped=skipped))
        if not components:
            return []

        # Uma consulta so: quais desses componentes ja foram baixados antes.
        keys = [component.source_key for component in components]
        already = set(
            StockMovement.all_objects.filter(
                account=order.account,
                source_key__in=keys,
                deleted_at__isnull=True,
            ).values_list("source_key", flat=True)
        )

        created = []
        for component in components:
            if component.source_key in already:
                continue
            quantity = component.quantity.quantize(QUANTITY_PLACES)
            if quantity <= 0:
                continue
            unit_cost = Decimal(str(component.unit_cost or 0))
            movement = StockMovement.objects.create(
                account=order.account,
                restaurant=order.restaurant,
                branch=order.branch,
                ingredient=component.ingredient,
                location=location,
                order_item=component.order_item,
                operator=user,
                movement_type=StockMovement.TYPE_SALE,
                quantity=-quantity,
                unit_cost=unit_cost,
                total_cost=-(quantity * unit_cost).quantize(MONEY_PLACES),
                reason=f"Baixa automatica do pedido {order.sequence}",
                source_key=component.source_key,
                source_snapshot=component.snapshot,
                created_by=user,
                updated_by=user,
            )
            created.append(movement)
            record_audit(
                action=AuditLog.ACTION_CREATED,
                instance=movement,
                actor=user,
                metadata={"auto": True, "source_key": component.source_key},
            )

        if skipped:
            record_audit(
                action=AuditLog.ACTION_UPDATED,
                instance=order,
                actor=user,
                metadata={"event": "stock_deduction_skipped", "skipped": skipped},
            )
        return created


@transaction.atomic
def revert_order_stock(*, order, user, reason=""):
    """Devolve ao estoque o que a venda baixou — cancelamento ou estorno.

    Cria movimentos INVERSOS em vez de apagar os originais: o livro e imutavel,
    e apagar a baixa esconderia que o insumo chegou a sair. A reversao tambem
    tem chave propria, entao chamar duas vezes nao devolve em dobro.

    NAO e chamada automaticamente por `cancel_order`, e isso e deliberado:
    quando a baixa acontece no envio para a cozinha, o prato ja foi feito, e um
    item preparado que o cliente desistiu de levar e perda, nao insumo de volta
    na geladeira. A devolucao e uma decisao operacional — quem cancela precisa
    dizer que o insumo voltou —, entao ela fica exposta como acao propria.
    """
    with tenant_context(order.account):
        originals = StockMovement.objects.filter(
            account=order.account,
            movement_type=StockMovement.TYPE_SALE,
            order_item__order=order,
        ).select_related("ingredient", "location")

        already = set(
            StockMovement.all_objects.filter(
                account=order.account,
                reversal_of__in=originals,
                deleted_at__isnull=True,
            ).values_list("reversal_of_id", flat=True)
        )

        created = []
        for original in originals:
            if original.id in already:
                continue
            movement = StockMovement.objects.create(
                account=original.account,
                restaurant=original.restaurant,
                branch=original.branch,
                ingredient=original.ingredient,
                location=original.location,
                order_item=original.order_item,
                operator=user,
                movement_type=StockMovement.TYPE_REVERSAL,
                quantity=-original.quantity,
                unit_cost=original.unit_cost,
                total_cost=-original.total_cost,
                reason=reason or f"Reversao da baixa do pedido {order.sequence}",
                source_key=f"reversal:{original.source_key}" if original.source_key else "",
                source_snapshot={"reverses": str(original.id), **(original.source_snapshot or {})},
                reversal_of=original,
                created_by=user,
                updated_by=user,
            )
            created.append(movement)
            record_audit(
                action=AuditLog.ACTION_CREATED,
                instance=movement,
                actor=user,
                metadata={"reversal_of": str(original.id)},
            )
        return created
