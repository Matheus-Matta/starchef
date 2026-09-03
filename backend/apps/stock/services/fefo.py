import logging
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.stock.models import InventoryLot, StockMovement

logger = logging.getLogger(__name__)


def consume_stock_fefo(
    account,
    product,
    location,
    quantity,
    operator,
    movement_type=StockMovement.TYPE_SALE_OUTPUT,
    order_item=None,
    reason="",
    restaurant=None,
    branch=None,
):
    """
    Consome quantidade do estoque de um produto utilizando a regra FEFO (First Expire, First Out).
    Prioriza lotes com data de validade mais próxima.
    """
    if quantity <= 0:
        raise ValidationError("Quantidade a ser consumida deve ser maior que zero.")

    restaurant = restaurant or getattr(product, "restaurant", None)
    branch = branch or getattr(product, "branch", None)

    remaining_to_consume = Decimal(str(quantity))
    consumed_movements = []

    with transaction.atomic():
        # Buscar lotes disponíveis ordenados por validade (nulls por último) e depois por data de entrada
        available_lots = (
            InventoryLot.all_objects.select_for_update()
            .filter(
                account=account,
                product=product,
                location=location,
                status=InventoryLot.STATUS_ACTIVE,
                available_quantity__gt=0,
            )
            .order_by(
                models_fefo_order(),
                "received_at",
            )
        )

        for lot in available_lots:
            if remaining_to_consume <= 0:
                break

            consume_from_lot = min(lot.available_quantity, remaining_to_consume)
            lot.available_quantity -= consume_from_lot
            if lot.available_quantity <= 0:
                lot.status = InventoryLot.STATUS_CONSUMED
            lot.save(update_fields=["available_quantity", "status"])

            # Registrar movimento
            movement = StockMovement.objects.create(
                account=account,
                restaurant=restaurant,
                branch=branch,
                product=product,
                location=location,
                inventory_lot=lot,
                order_item=order_item,
                operator=operator,
                movement_type=movement_type,
                quantity=-consume_from_lot,
                stock_unit=product.stock_unit,
                unit_cost=lot.unit_cost,
                total_cost=consume_from_lot * lot.unit_cost,
                reason=reason or f"Consumo FEFO Lote {lot.lot_number}",
            )
            consumed_movements.append(movement)
            remaining_to_consume -= consume_from_lot

        # Se ainda resta saldo para consumir (sem lotes suficientes)
        if remaining_to_consume > 0:
            if not product.allow_negative_stock and product.tracking_mode == product.TRACKING_LOT:
                raise ValidationError(
                    f"Saldo insuficiente em lotes ativos para '{product.name}'. "
                    f"Faltam {remaining_to_consume} {product.stock_unit}."
                )

            # Consumo residual sem lote vinculado
            movement = StockMovement.objects.create(
                account=account,
                restaurant=restaurant,
                branch=branch,
                product=product,
                location=location,
                order_item=order_item,
                operator=operator,
                movement_type=movement_type,
                quantity=-remaining_to_consume,
                stock_unit=product.stock_unit,
                unit_cost=product.current_average_cost,
                total_cost=remaining_to_consume * product.current_average_cost,
                reason=reason or "Consumo de estoque residual / sem lote",
            )
            consumed_movements.append(movement)

    return consumed_movements


def models_fefo_order():
    from django.db.models import F
    return F("expiration_date").asc(nulls_last=True)
