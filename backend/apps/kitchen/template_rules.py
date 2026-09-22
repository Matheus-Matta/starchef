"""Regras iniciais dos modelos de estação, com destinos reais das colunas."""


def _rule(identifier, name, action, conditions, priority, target=None):
    return {
        "id": identifier,
        "name": name,
        "action": action,
        "match": "all",
        "conditions": conditions,
        "target_column": str(target.pk) if target else None,
        "enabled": True,
        "priority": priority,
    }


def template_rules(columns, *, include_cancelled=False):
    """Recebe itens em produção e acompanha mudanças reais de status.

    Tempo de SLA gera alerta no KDS; nunca conclui produção sozinho. A regra de
    preparo só tira cards da entrada, para não desfazer a montagem manual.
    """
    done = next(column for column in columns if column.is_done)
    cancelled = next((column for column in columns if column.name == "Cancelados"), None) if include_cancelled else None
    preparing = next(
        (column for column in columns if not column.is_entry and not column.is_done and column != cancelled), None
    )
    rules = [
        _rule("receive-active", "Receber itens em produção", "include", [], 0),
        _rule("hide-cancelled-orders", "Ocultar pedidos cancelados", "exclude", [
            {"field": "order_status", "operator": "equals", "value": "cancelled"}
        ], 1),
        _rule("hide-refunded-orders", "Ocultar pedidos estornados", "exclude", [
            {"field": "order_status", "operator": "equals", "value": "refunded"}
        ], 2),
        _rule("hide-cancelled-items", "Ocultar itens cancelados", "exclude", [
            {"field": "item_status", "operator": "equals", "value": "cancelled"}
        ], 3),
        _rule("move-ready", "Mover itens prontos para a última coluna", "move", [
            {"field": "item_status", "operator": "equals", "value": "ready"}
        ], 4, done),
    ]
    if preparing:
        rules.append(_rule("move-preparing", "Mover itens em preparo ao sair da entrada", "move", [
            {"field": "item_status", "operator": "equals", "value": "preparing"},
            {"field": "column_is_entry", "operator": "true", "value": None},
        ], 5, preparing))
    if cancelled:
        rules = [rule for rule in rules if rule["id"] not in {
            "hide-cancelled-orders", "hide-cancelled-items",
        }]
        rules.insert(1, _rule("move-cancelled", "Mover itens cancelados para Cancelados", "move", [
            {"field": "item_status", "operator": "equals", "value": "cancelled"},
        ], 0, cancelled))
    return rules
