from decimal import Decimal

from django.db import transaction

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.stock.models import StockLocation, StockMovement


@transaction.atomic
def deduct_order_stock(*, order, user):
    with tenant_context(order.account):
        default_location, _ = StockLocation.objects.get_or_create(
            restaurant=order.restaurant,
            branch=order.branch,
            name="Principal",
            defaults={
                "account": order.account,
                "created_by": user,
                "updated_by": user,
            },
        )

        created_movements = []
        for item in order.items.select_related("product").prefetch_related("product__recipe__items__ingredient"):
            recipe = getattr(item.product, "recipe", None)
            if not recipe or not recipe.auto_deduct_stock:
                continue
            for recipe_item in recipe.items.all():
                quantity = Decimal(recipe_item.quantity) * Decimal(item.quantity)
                movement = StockMovement.objects.create(
                    account=order.account,
                    restaurant=order.restaurant,
                    branch=order.branch,
                    ingredient=recipe_item.ingredient,
                    location=default_location,
                    order_item=item,
                    operator=user,
                    movement_type=StockMovement.TYPE_SALE,
                    quantity=-quantity,
                    unit_cost=recipe_item.ingredient_cost,
                    total_cost=-(quantity * recipe_item.ingredient_cost),
                    reason=f"Auto deduction from order {order.sequence}",
                    created_by=user,
                    updated_by=user,
                )
                created_movements.append(movement)
                record_audit(action=AuditLog.ACTION_CREATED, instance=movement, actor=user, metadata={"auto": True})

        return created_movements
