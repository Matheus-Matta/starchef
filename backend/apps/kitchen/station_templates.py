"""
Modelos (templates) de estação de KDS — atalhos de onboarding.

Cada template descreve um quadro pronto para um tipo de operação (cozinha, bar,
pizzaria…), já com as colunas montadas. O cliente escolhe um modelo ao criar a
estação e o backend cria o quadro + colunas de uma vez (ver
`KdsStationViewSet.from_template`). As cores seguem a paleta padrão do KDS.
"""

STATION_TEMPLATES = [
    {
        "key": "cozinha",
        "name": "Cozinha",
        "icon": "soup",
        "description": "Fluxo padrão de cozinha: a fazer, preparo, montagem e pronto.",
        "sectors": ["kitchen"],
        "columns": [
            {"name": "A fazer", "color": "#64748b", "is_entry": True, "is_done": False},
            {"name": "Em preparo", "color": "#0ea5e9", "is_entry": False, "is_done": False},
            {"name": "Montagem", "color": "#8b5cf6", "is_entry": False, "is_done": False},
            {"name": "Pronto", "color": "#10b981", "is_entry": False, "is_done": True},
        ],
    },
    {
        "key": "bar",
        "name": "Bar / Bebidas",
        "icon": "glass-water",
        "description": "Preparo de bebidas: fila, preparando e pronto.",
        "sectors": ["bar"],
        "columns": [
            {"name": "Fila", "color": "#64748b", "is_entry": True, "is_done": False},
            {"name": "Preparando", "color": "#6366f1", "is_entry": False, "is_done": False},
            {"name": "Pronto", "color": "#10b981", "is_entry": False, "is_done": True},
        ],
    },
    {
        "key": "pizzaria",
        "name": "Pizzaria",
        "icon": "pizza",
        "description": "Massa, montagem, forno e pronto.",
        "sectors": ["kitchen"],
        "columns": [
            {"name": "Massa", "color": "#64748b", "is_entry": True, "is_done": False},
            {"name": "Montagem", "color": "#f59e0b", "is_entry": False, "is_done": False},
            {"name": "Forno", "color": "#ef4444", "is_entry": False, "is_done": False},
            {"name": "Pronto", "color": "#10b981", "is_entry": False, "is_done": True},
        ],
    },
    {
        "key": "confeitaria",
        "name": "Confeitaria / Sobremesas",
        "icon": "cake",
        "description": "A fazer, preparo, finalização e pronto.",
        "sectors": ["dessert"],
        "columns": [
            {"name": "A fazer", "color": "#64748b", "is_entry": True, "is_done": False},
            {"name": "Preparo", "color": "#0ea5e9", "is_entry": False, "is_done": False},
            {"name": "Finalização", "color": "#ec4899", "is_entry": False, "is_done": False},
            {"name": "Pronto", "color": "#10b981", "is_entry": False, "is_done": True},
        ],
    },
    {
        "key": "simples",
        "name": "Simples",
        "icon": "columns",
        "description": "Dois passos: a fazer e pronto.",
        "sectors": [],
        "columns": [
            {"name": "A fazer", "color": "#64748b", "is_entry": True, "is_done": False},
            {"name": "Pronto", "color": "#10b981", "is_entry": False, "is_done": True},
        ],
    },
]

TEMPLATES_BY_KEY = {t["key"]: t for t in STATION_TEMPLATES}
