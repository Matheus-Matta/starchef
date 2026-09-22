from django.utils import timezone

from apps.orders.models import OrderItem
from apps.orders.services import update_order_item_status

from .models import KdsItemPosition


def _minutes_since(value, now):
    return max(0, int((now - value).total_seconds() // 60)) if value else 0


def _context(item, position, now):
    """O contexto que as regras da estação avaliam.

    `order` aqui é o pedido de PRODUÇÃO: numa conta agrupada, `item.order`
    passa a ser o pedido consolidado, que não tem mesa nem comanda. Uma regra
    como "atrasa se for comanda" viraria "é balcão" no instante em que o caixa
    começa a fechar a conta — e fechar a conta é justamente quando a cozinha
    ainda pode estar montando a sobremesa.

    O financeiro continua vindo do pedido ATUAL (é ele que está sendo pago).
    """
    production_order = item.order
    current_order = item.order
    return {
        "order_type": production_order.order_type,
        "production_sector": item.production_sector,
        "item_status": item.status,
        "order_status": current_order.status,
        "payment_status": current_order.payment_status,
        "production_status": current_order.production_status,
        "delivery_status": current_order.delivery_status,
        "minutes_since_sent": _minutes_since(item.sent_to_kitchen_at or item.launched_at, now),
        "minutes_in_column": _minutes_since(position.entered_at if position else None, now),
        "column_is_entry": bool(position and position.column.is_entry),
        "has_customer_note": bool(item.customer_note),
        "has_table": bool(production_order.table_id),
        "has_command": bool(item.command_id or production_order.command_id),
    }


def _condition_matches(condition, context):
    actual, expected = context.get(condition.get("field")), condition.get("value")
    operator = condition.get("operator")
    if operator == "true":
        return bool(actual)
    if operator == "false":
        return not actual
    if operator in {"in", "not_in"}:
        found = actual in (expected if isinstance(expected, list) else [expected])
        return found if operator == "in" else not found
    if operator in {"gte", "lte"}:
        try:
            left, right = float(actual), float(expected)
        except (TypeError, ValueError):
            return False
        return left >= right if operator == "gte" else left <= right
    if operator == "not_equals":
        return str(actual) != str(expected)
    return str(actual) == str(expected)


def _rule_matches(rule, context):
    results = [_condition_matches(condition, context) for condition in rule.get("conditions") or []]
    return any(results) if rule.get("match") == "any" and results else all(results)


def _included(rules, context):
    active = [rule for rule in rules if rule.get("enabled", True)]
    includes = [rule for rule in active if rule.get("action") == "include"]
    excludes = [rule for rule in active if rule.get("action") == "exclude"]
    if any(_rule_matches(rule, context) for rule in excludes):
        return False
    return not includes or any(_rule_matches(rule, context) for rule in includes)


def move_position(position, column, item, user):
    if position.column_id == column.id:
        return item
    if column.is_done and item.status != OrderItem.STATUS_READY:
        item = update_order_item_status(item, OrderItem.STATUS_READY, user)
    elif not column.is_done and not column.is_entry and item.status == OrderItem.STATUS_SENT:
        item = update_order_item_status(item, OrderItem.STATUS_PREPARING, user)
    position.column = column
    position.entered_at = timezone.now()
    position.updated_by = user
    position.save(update_fields=["column", "entered_at", "updated_by", "updated_at"])
    item.kds_column = column  # compatibilidade com clientes anteriores
    item.save(update_fields=["kds_column", "updated_at"])
    return item


def apply_station_rules(items, station, user):
    """Resolve inclusão/movimentos automáticos e devolve IDs visíveis."""
    columns = {str(column.id): column for column in station.columns.filter(is_active=True)}
    entry = next((column for column in columns.values() if column.is_entry), None)
    entry = entry or next(iter(columns.values()), None)
    if entry is None:
        return []
    rules = sorted(station.rules or [], key=lambda rule: rule.get("priority", 0))
    positions = {
        position.item_id: position
        for position in KdsItemPosition.objects.filter(station=station, item__in=items).select_related("column")
    }
    now, visible = timezone.now(), []
    for item in items:
        position = positions.get(item.id)
        context = _context(item, position, now)
        if station.sectors and item.production_sector not in station.sectors:
            continue
        if not _included(rules, context):
            continue
        if position is None:
            position, _ = KdsItemPosition.objects.get_or_create(
                station=station, item=item,
                defaults={
                    "account": station.account, "column": entry,
                    "created_by": user, "updated_by": user,
                },
            )
            positions[item.id] = position
            context = _context(item, position, now)
        for rule in rules:
            if rule.get("enabled", True) and rule.get("action") == "move" and _rule_matches(rule, context):
                target = columns.get(str(rule.get("target_column")))
                if target:
                    move_position(position, target, item, user)
                break
        visible.append(item.id)
    return visible
