"""IDs reais do tenant + criacao do cenario minimo de carga.

Sem isto o teste mede validacao de chave estrangeira. Com isto ele mede o que
interessa: o caminho completo de uma venda, com produto que existe, comanda que
existe e forma de pagamento que existe.
"""
COLLECTIONS = {
    "restaurants": "/api/v1/restaurants/",
    "branches": "/api/v1/branches/",
    "sectors": "/api/v1/tables/sectors/",
    "tables": "/api/v1/tables/",
    "commands": "/api/v1/commands/",
    "categories": "/api/v1/menu/categories/",
    "products": "/api/v1/menu/products/",
    "ingredients": "/api/v1/menu/ingredients/",
    "recipes": "/api/v1/menu/recipes/",
    "menus": "/api/v1/menu/menus/",
    "customers": "/api/v1/customers/",
    "payment_methods": "/api/v1/payments/methods/",
    "cash_stations": "/api/v1/cash-stations/",
    "kitchen_stations": "/api/v1/kitchen/stations/",
    "printers": "/api/v1/printers/",
    "scales": "/api/v1/scales/",
    "suppliers": "/api/v1/stock/suppliers/",
    "stock_locations": "/api/v1/stock/locations/",
    "users": "/api/v1/users/",
    "roles": "/api/v1/roles/",
    "plans": "/api/v1/plans/",
    "orders": "/api/v1/orders/",
}

PREFIX = "LT"


def _results(payload):
    if isinstance(payload, dict):
        return payload.get("results") or []
    return payload or []


class RefPool:
    """Colecoes de IDs conhecidos + os objetos que o fluxo de venda precisa."""

    def __init__(self, session):
        self.session = session
        self.ids = {name: [] for name in COLLECTIONS}
        self.objects = {}
        self.restaurant = None
        self.kg_product = None
        self.unit_products = []
        self.cash_station = None
        self.scale = None
        self.printer = None
        self.payment_by_type = {}
        self.command_codes = []

    def pick(self, collection, r):
        valores = self.ids.get(collection) or []
        return r.choice(valores) if valores else None

    def sample(self, collection, r, quantidade):
        valores = self.ids.get(collection) or []
        if not valores or quantidade <= 0:
            return []
        return r.sample(valores, min(quantidade, len(valores)))

    def load(self, page_size=100):
        for name, path in COLLECTIONS.items():
            data = self.session.json_get(f"{path}?page_size={page_size}")
            registros = _results(data)
            self.ids[name] = [str(item["id"]) for item in registros if isinstance(item, dict) and item.get("id")]
            self.objects[name] = registros
        self._resolve_key_objects()
        return self

    def _perfil_restaurant_id(self):
        """O restaurante do PERFIL manda: e o escopo em que a venda vai valer."""
        me = self.session.user or {}
        alvo = me.get("restaurant_id") or (me.get("profile") or {}).get("restaurant")
        if isinstance(alvo, dict):
            return str(alvo.get("id") or "")
        return str(alvo or "")

    def _resolve_key_objects(self):
        restaurantes = self.objects.get("restaurants") or []
        do_perfil = self._perfil_restaurant_id()
        self.restaurant = next(
            (r for r in restaurantes if str(r.get("id")) == do_perfil), restaurantes[0] if restaurantes else None
        )
        alvo = str((self.restaurant or {}).get("id") or "")
        if self.restaurant:
            # A conta tem mais de um restaurante; misturar os dois no mesmo
            # payload produz "objeto relacionado pertence a outro restaurante"
            # — recusa correta do backend e ruido puro no relatorio.
            self.objects["restaurants"] = [self.restaurant]
            self.ids["restaurants"] = [alvo]
        self._scope_pools(alvo)

        produtos = [p for p in self.objects.get("products") or [] if p.get("is_active", True)]
        self.kg_product = next((p for p in produtos if p.get("pricing_mode") == "kg"), None)
        self.unit_products = [p for p in produtos if p.get("pricing_mode") != "kg"] or produtos
        estacoes = self.objects.get("cash_stations") or []
        self.cash_station = estacoes[0] if estacoes else None
        balancas = self.objects.get("scales") or []
        self.scale = balancas[0] if balancas else None
        impressoras = self.objects.get("printers") or []
        self.printer = impressoras[0] if impressoras else None
        self.payment_by_type = {}
        for metodo in self.objects.get("payment_methods") or []:
            if metodo.get("is_active", True):
                self.payment_by_type.setdefault(metodo.get("method_type"), metodo)
        comandas = [c for c in self.objects.get("commands") or [] if c.get("is_active", True)]
        self.command_codes = [str(c.get("code") or c.get("number")) for c in comandas]

    def _scope_pools(self, restaurante_id):
        """Poda de cada colecao o que pertence a OUTRO restaurante.

        A API recusa referencia cruzada com "Objeto relacionado pertence a outro
        restaurante" — corretamente. Sem esta poda, o gerador produziria esse
        400 o tempo todo e o relatorio culparia o backend por acertar.
        """
        if not restaurante_id:
            return
        for nome, registros in self.objects.items():
            if nome == "restaurants" or not registros:
                continue
            if not isinstance(registros[0], dict) or "restaurant" not in registros[0]:
                continue
            # `restaurant` ausente/nulo = recurso compartilhado da conta; fica.
            do_escopo = [
                item for item in registros
                if not item.get("restaurant") or str(item["restaurant"]) == restaurante_id
            ]
            if do_escopo:
                self.objects[nome] = do_escopo
                self.ids[nome] = [str(item["id"]) for item in do_escopo if item.get("id")]

    def ensure_scenario(self, log=print):
        """Cria o que falta para uma venda completa existir (ver `scenario.py`)."""
        from .scenario import ensure_scenario

        return ensure_scenario(self, log=log)
