"""Monta um payload valido a partir do schema + IDs reais do tenant.

Um payload gerado so pelo tipo do campo cria UUID aleatorio em toda chave
estrangeira, e o backend recusa tudo com 400 — o teste viraria um medidor de
validacao de FK, nao de carga. Por isso o `RefPool` entra: campo que parece
referencia recebe um ID que existe de verdade.
"""

from . import fakes
from .valores import number_value, string_value

#: Sufixo do campo -> colecao do RefPool.
REFERENCE_HINTS = {
    "restaurant": "restaurants",
    "branch": "branches",
    "product": "products",
    "category": "categories",
    "customer": "customers",
    "payment_method": "payment_methods",
    "table": "tables",
    "sector": "sectors",
    "command": "commands",
    "scale": "scales",
    "printer": "printers",
    "supplier": "suppliers",
    "ingredient": "ingredients",
    "recipe": "recipes",
    "order": "orders",
    "user": "users",
    "role": "roles",
    "cash_station": "cash_stations",
    "station": "cash_stations",
    "location": "stock_locations",
    "menu": "menus",
    "plan": "plans",
    "parent": None,
}

#: O schema diz "nullable", mas o servidor exige quando nao ha cabecalho de
#: escopo: omitir virava "restaurant: obrigatorio" em payload valido.
TENANT_FIELDS = ("restaurant", "branch")

#: Marcador de "nao sei preencher esta referencia" — vira payload incerto.
_UNKNOWN_REFERENCE = object()


def _reference_pool(field, path=""):
    # `closed_by`, `approved_by`, `opened_by`: sempre um usuario.
    if field.endswith("_by"):
        return "users"
    # A mesma palavra "station" e caixa no PDV e estacao no KDS.
    if field == "station" and "/kitchen/" in path:
        return "kitchen_stations"
    for suffix, pool in REFERENCE_HINTS.items():
        if field == suffix or field.endswith(f"_{suffix}") or field == f"{suffix}_id":
            return pool
    return None


def _wants_reference(field, meta):
    """So e chave estrangeira quando o TIPO diz que e.

    `available_for_table` termina em `_table` e e um booleano. Decidir pelo nome
    sozinho colocava um UUID de mesa num campo sim/nao — e o 400 resultante
    aparecia no relatorio como se o backend estivesse errado.
    """
    if meta.get("format") == "uuid":
        return True
    items = meta.get("items") or {}
    if meta.get("type") == "array" and items.get("format") == "uuid":
        return True
    # Inteiro so e referencia quando se chama exatamente como ela (`user`,
    # `user_id`). `display_order` termina em `_order` e e uma posicao, nao um
    # pedido — mandar UUID nele virava "suspeita" falsa a cada execucao.
    if meta.get("type") != "integer":
        return False
    if field.endswith("_by") or field.endswith("_user"):
        return True
    return any(field in (suffix, f"{suffix}_id") for suffix in REFERENCE_HINTS)


class PayloadBuilder:
    """Gera payloads validos (e variados) para um `EndpointSchema`."""

    def __init__(self, refs, optional_ratio=0.65):
        self.refs = refs
        self.optional_ratio = optional_ratio

    def value_for(self, field, meta, r, limpo=True, obrigatorio=False, path=""):
        referencia = _wants_reference(field, meta)
        pool = _reference_pool(field, path) if referencia else None
        if pool:
            chosen = self.refs.pick(pool, r)
            if chosen:
                return chosen
        if referencia and not pool:
            # FK que o pool nao conhece (perfil fiscal, etc.). Inventar um UUID
            # daria 400 garantido — informacao zero sobre o sistema.
            return _UNKNOWN_REFERENCE if obrigatorio else None
        if pool and meta.get("nullable"):
            return None
        kind = meta.get("type")
        if kind == "boolean":
            return r.random() < 0.75
        if kind in ("number", "integer"):
            return number_value(field, meta, r, limpo)
        if kind == "array":
            items = meta.get("items") or {}
            if items.get("format") == "uuid" and pool:
                minimo = 1 if obrigatorio else 0
                return self.refs.sample(pool, r, r.randint(minimo, 2)) or self.refs.sample(pool, r, minimo)
            if items.get("enum"):
                return [r.choice(items["enum"])]
            return []
        if kind == "object":
            return {"origem": "loadtest", "nota": fakes.texto(r, curto=True)}
        return string_value(field, meta, r, limpo)

    def build(self, schema, r, overrides=None, sloppy_ratio=0.0):
        """Devolve (payload, desleixado).

        `desleixado` marca o payload que saiu com o preenchimento tosco de um
        operador apressado — CPF com digito errado, e-mail sem arroba, campo em
        branco. Ele nao e "invalido de proposito": aceitar ou recusar sao os
        dois comportamentos defensaveis, e o relatorio so cobra que nao quebre.
        """
        desleixado = r.random() < sloppy_ratio
        incerto = False
        payload = {}
        campos = list(schema.writable.items())
        sujo = r.choice(campos)[0] if (desleixado and campos) else None
        for field, meta in campos:
            obrigatorio = field in schema.required or field in TENANT_FIELDS
            if not obrigatorio and r.random() > self.optional_ratio:
                continue
            value = self.value_for(field, meta, r, limpo=(field != sujo), obrigatorio=obrigatorio, path=schema.path)
            if value is None and not obrigatorio:
                continue
            if value is _UNKNOWN_REFERENCE:
                payload[field] = fakes.uuid4(r)
                incerto = True
                continue
            payload[field] = value
        if overrides:
            payload.update(overrides)
        return payload, incerto or (desleixado and sujo in payload)
