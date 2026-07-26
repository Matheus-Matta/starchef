"""Serviços de domínio dos cadastros base (restaurantes/mesas/comandas)."""
from django.db.models import Max

from apps.core.tenant import tenant_context
from apps.restaurants.models import Command


def next_command_number(restaurant):
    """Próximo número de comanda do restaurante (max+1), escopo por restaurante.

    Espelha `apps.orders.services.next_order_sequence`. Usa `all_objects` para
    considerar também comandas inativas/soft-deleted e não repetir números.
    """
    with tenant_context(restaurant.account):
        last = Command.all_objects.filter(restaurant=restaurant).aggregate(value=Max("number"))["value"] or 0
        return last + 1


def default_command_code(number):
    """Código escaneável padrão a partir do número (zero-padded, ex.: 1 -> "0001")."""
    return f"{int(number):04d}"
