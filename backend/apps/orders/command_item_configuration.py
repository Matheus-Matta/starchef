from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError

from apps.core.numbers import parse_quantity
from apps.menu.models import ProductVariation


TWO_PLACES = Decimal("0.01")


def configured_values(*, product, quantity, variations=None, addons=None, base_price=None):
    """Valida as escolhas do modal e calcula o retrato financeiro do item."""
    parsed_quantity = parse_quantity(quantity, default=1)
    variation_ids = _ids(variations)
    selected_variations = list(
        ProductVariation.objects.filter(
            product=product,
            is_active=True,
            id__in=variation_ids,
        ).order_by("id")
    )
    if len(selected_variations) != len(set(map(str, variation_ids))):
        raise ValidationError("Uma ou mais variações não pertencem ao produto.")
    if product.requires_variation and not selected_variations:
        raise ValidationError("Selecione uma variação obrigatória.")

    addon_ids = _ids(addons)
    selected_addons = list(product.addons.filter(is_active=True, id__in=addon_ids).order_by("id"))
    if len(selected_addons) != len(set(map(str, addon_ids))):
        raise ValidationError("Um ou mais adicionais não pertencem ao produto.")

    variation_snapshot = [
        {"id": str(item.id), "name": item.name, "price_delta": str(item.price_delta)} for item in selected_variations
    ]
    extras = sum((item.price_delta for item in selected_variations), Decimal("0.00"))
    extras += sum((item.price for item in selected_addons), Decimal("0.00"))
    unit_price = (base_price if base_price is not None else product.current_price) + extras
    total_price = (unit_price * parsed_quantity).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return parsed_quantity, unit_price, total_price, variation_snapshot, selected_addons


def _ids(entries):
    values = [entry.get("id") if isinstance(entry, dict) else entry for entry in (entries or [])]
    return [value for value in values if value]
