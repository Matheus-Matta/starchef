from django.core.exceptions import ValidationError

from apps.printers.models import ScaleReading


def build_first_item_data(*, raw_item, request_data, account):
    """Turn the sale draft's first line into arguments for `add_order_item`."""
    reading = None
    reading_id = raw_item.get("scale_reading")
    if reading_id:
        try:
            reading = ScaleReading.objects.select_related("scale").get(
                pk=reading_id,
                account=account,
            )
        except (ScaleReading.DoesNotExist, TypeError, ValueError, ValidationError) as exc:
            raise ValidationError("Leitura de balanca nao encontrada.") from exc

    return {
        "quantity": raw_item.get("quantity"),
        "scale_reading": reading,
        "weight_kg": raw_item.get("weight_kg"),
        "variations": raw_item.get("variations", []),
        "addons": raw_item.get("addons", []),
        "customer_note": raw_item.get("customer_note", ""),
        "expected_unit_price": raw_item.get("expected_unit_price"),
        # The operator code can be sent once for the whole order or per item.
        "metafields": raw_item.get("metafields") or request_data.get("metafields"),
    }
