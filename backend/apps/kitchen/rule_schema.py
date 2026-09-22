from rest_framework import serializers

DEFAULT_STATION_RULES = [
    {
        "id": "include-all",
        "name": "Incluir todos os pedidos",
        "action": "include",
        "match": "all",
        "conditions": [],
        "target_column": None,
        "enabled": True,
        "priority": 0,
    }
]

FIELDS = {
    "order_type", "production_sector", "item_status", "order_status",
    "payment_status", "production_status", "delivery_status",
    "minutes_since_sent", "minutes_in_column", "has_customer_note",
    "has_table", "has_command", "column_is_entry",
}
OPERATORS = {"equals", "not_equals", "in", "not_in", "gte", "lte", "true", "false"}
ACTIONS = {"include", "exclude", "move"}


def validate_station_rules(value, station=None):
    if not isinstance(value, list):
        raise serializers.ValidationError("As regras precisam ser uma lista.")
    if len(value) > 50:
        raise serializers.ValidationError("Uma estação aceita no máximo 50 regras.")

    column_ids = {str(column.id) for column in station.columns.all()} if station else None
    normalized = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise serializers.ValidationError(f"A regra {index + 1} é inválida.")
        action = raw.get("action")
        if action not in ACTIONS:
            raise serializers.ValidationError(f"Ação inválida na regra {index + 1}.")
        conditions = raw.get("conditions", [])
        if not isinstance(conditions, list) or len(conditions) > 10:
            raise serializers.ValidationError(f"Condições inválidas na regra {index + 1}.")
        clean_conditions = []
        for condition in conditions:
            if not isinstance(condition, dict) or condition.get("field") not in FIELDS:
                raise serializers.ValidationError(f"Campo inválido na regra {index + 1}.")
            if condition.get("operator") not in OPERATORS:
                raise serializers.ValidationError(f"Operador inválido na regra {index + 1}.")
            clean_conditions.append({
                "field": condition["field"], "operator": condition["operator"],
                "value": condition.get("value"),
            })
        target = raw.get("target_column") or None
        if action == "move" and not target:
            raise serializers.ValidationError(f"A regra {index + 1} precisa de uma coluna de destino.")
        if target and column_ids is not None and str(target) not in column_ids:
            raise serializers.ValidationError(f"A coluna da regra {index + 1} não pertence à estação.")
        try:
            priority = int(raw.get("priority", index))
        except (TypeError, ValueError):
            raise serializers.ValidationError(f"Prioridade inválida na regra {index + 1}.") from None
        normalized.append({
            "id": str(raw.get("id") or f"rule-{index + 1}"),
            "name": str(raw.get("name") or f"Regra {index + 1}")[:100],
            "action": action,
            "match": "any" if raw.get("match") == "any" else "all",
            "conditions": clean_conditions,
            "target_column": str(target) if target else None,
            "enabled": bool(raw.get("enabled", True)),
            "priority": max(0, min(priority, 999)),
        })
    return normalized
