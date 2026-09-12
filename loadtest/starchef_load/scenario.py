"""Cria o cenario minimo de uma venda quando ele nao existe na conta.

Separado de `refs.py` porque sao duas responsabilidades: la se descobre o que
existe; aqui se cria o que falta. Roda uma vez por execucao e e praticamente
idempotente — so cria o que nao encontrou.
"""
from .refs import COLLECTIONS, PREFIX


def _create(pool, collection, payload):
    response = pool.session.post(COLLECTIONS[collection], payload)
    if response.status in (200, 201):
        return response.json()
    return None


def ensure_scenario(pool, log=print):
    """Cria o que falta para uma venda completa existir. Idempotente na pratica."""
    criados = []
    if not pool.restaurant:
        raise RuntimeError("nenhum restaurante na conta — rode `manage.py seed_demo` antes")
    restaurante = str(pool.restaurant["id"])

    if not pool.objects.get("categories"):
        if _create(pool, "categories", {"name": f"{PREFIX} Carga", "restaurant": restaurante}):
            criados.append("categoria")

    if not pool.kg_product:
        categoria = (pool.objects.get("categories") or [{}])[0].get("id")
        produto = _create(pool, "products", {
            "name": f"{PREFIX} Buffet por Kg",
            "internal_code": f"{PREFIX}KG",
            "price": "69.90",
            "pricing_mode": "kg",
            "product_type": "meal",
            "category": categoria,
            "restaurants": [restaurante],
            "is_active": True,
        })
        if produto:
            criados.append("produto por kg")
    if len(pool.unit_products) < 3:
        categoria = (pool.objects.get("categories") or [{}])[0].get("id")
        for indice in range(3):
            if _create(pool, "products", {
                "name": f"{PREFIX} Item {indice + 1}",
                "internal_code": f"{PREFIX}U{indice + 1}",
                "price": f"{12 + indice * 7}.50",
                "pricing_mode": "unit",
                "product_type": "meal",
                "category": categoria,
                "restaurants": [restaurante],
                "is_active": True,
            }):
                criados.append("produto unitario")

    for tipo, nome in (("cash", "Dinheiro"), ("card", "Cartao"), ("pix", "PIX")):
        if tipo not in pool.payment_by_type:
            if _create(pool, "payment_methods", {"name": f"{PREFIX} {nome}", "method_type": tipo, "is_active": True}):
                criados.append(f"forma {tipo}")

    if not pool.cash_station:
        if _create(pool, "cash_stations", {
            "restaurant": restaurante, "name": f"{PREFIX} Caixa 1", "code": f"{PREFIX}C1", "is_active": True,
        }):
            criados.append("estacao de caixa")

    if len(pool.command_codes) < 40:
        pool.session.post("/api/v1/commands/bulk-create/", {
            "restaurant": restaurante, "from_number": 1, "to_number": 200,
        })
        criados.append("comandas 1..200")

    if not pool.printer:
        if _create(pool, "printers", {
            "name": f"{PREFIX} Impressora", "restaurant": restaurante,
            "connection_type": "network", "driver_type": "escpos",
            "endpoint": "127.0.0.1", "is_active": True,
        }):
            criados.append("impressora")

    pool.load()
    if not pool.scale and pool.kg_product:
        payload = {
            "name": f"{PREFIX} Balanca", "restaurant": restaurante, "protocol": "generic",
            "port": "COM9", "product": str(pool.kg_product["id"]), "is_active": True,
        }
        if pool.printer:
            payload["printer"] = str(pool.printer["id"])
        if _create(pool, "scales", payload):
            criados.append("balanca")
        pool.load()
    if criados:
        log(f"[bootstrap] criados: {', '.join(sorted(set(criados)))}")
    return pool
