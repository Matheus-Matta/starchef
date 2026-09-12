"""Mutacoes que estragam um payload valido — cada uma com sua expectativa.

A regra que o teste cobra: **erro do cliente vira 4xx com mensagem; nunca 5xx,
nunca 2xx silencioso**. Quem aceita lixo (`GARBAGE_ACCEPTED`) e tao defeito
quanto quem quebra.
"""
import json

from . import result as verdicts

LONG = "A" * 5000
DEEP = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": {"j": 1}}}}}}}}}}


def _required(schema):
    return [f for f in schema.required if f in schema.fields]


def drop_required(payload, schema, r):
    campos = _required(schema)
    if not campos:
        return None
    payload.pop(r.choice(campos), None)
    return verdicts.REJECT


def null_required(payload, schema, r):
    campos = _required(schema)
    if not campos:
        return None
    payload[r.choice(campos)] = None
    return verdicts.REJECT


#: Valor errado POR TIPO. Mandar `True` num campo booleano nao e tipo errado —
#: e um booleano. O relatorio marcava a aceitacao correta como "lixo aceito".
WRONG_BY_TYPE = {
    "boolean": ["talvez", 42, ["sim"], {"valor": True}],
    "integer": ["muito", ["lista"], {"obj": 1}, "R$ 12,50"],
    "number": ["muito", ["lista"], {"obj": 1}, "R$ 12,50"],
}


def wrong_type(payload, schema, r):
    alvos = [f for f, meta in schema.fields.items() if meta.get("type") in WRONG_BY_TYPE]
    if not alvos:
        return None
    campo = r.choice(alvos)
    payload[campo] = r.choice(WRONG_BY_TYPE[schema.fields[campo]["type"]])
    return verdicts.REJECT


def too_long(payload, schema, r):
    alvos = [f for f, meta in schema.fields.items() if meta.get("max_length")]
    if not alvos:
        return None
    campo = r.choice(alvos)
    payload[campo] = LONG[: schema.fields[campo]["max_length"] + 200]
    return verdicts.REJECT


def bad_enum(payload, schema, r):
    alvos = [f for f, meta in schema.fields.items() if meta.get("enum")]
    if not alvos:
        return None
    payload[r.choice(alvos)] = "valor_que_nao_existe"
    return verdicts.REJECT


#: Campos que existem NEGATIVOS de proposito: um delta de variacao que abate do
#: preco, a margem de quem vende abaixo do custo, a diferenca de caixa que
#: faltou. Cobrar sinal positivo neles marcaria acerto como defeito.
SIGNED_FIELDS = ("delta", "difference", "margin", "balance", "change", "adjust", "variation")


def negative_money(payload, schema, r):
    alvos = [
        f for f in payload
        if any(t in f for t in ("price", "amount", "total", "quantity", "weight", "cost"))
        and not any(assinado in f for assinado in SIGNED_FIELDS)
        # Movimento de estoque: o sinal da quantidade e a direcao (saida < 0).
        and not (f == "quantity" and "/stock/movements/" in getattr(schema, "path", ""))
    ]
    if not alvos:
        return None
    payload[r.choice(alvos)] = r.choice([-1, -999.99, "-50"])
    return verdicts.REJECT


def broken_reference(payload, schema, r):
    alvos = [f for f, meta in schema.fields.items() if meta.get("format") == "uuid" and f in payload]
    if not alvos:
        return None
    payload[r.choice(alvos)] = r.choice(["nao-e-uuid", "00000000-0000-0000-0000-000000000000", 12345])
    return verdicts.REJECT


def huge_number(payload, schema, r):
    alvos = [f for f, meta in schema.fields.items() if meta.get("type") in ("number", "integer")]
    if not alvos:
        return None
    payload[r.choice(alvos)] = r.choice([10**30, -(10**30), 1e308, "9" * 40])
    return verdicts.REJECT


def not_a_number(payload, schema, r):
    alvos = [f for f, meta in schema.fields.items() if meta.get("type") in ("number", "integer")]
    if not alvos:
        return None
    payload[r.choice(alvos)] = r.choice(["NaN", "Infinity", "-Infinity", "1e999"])
    return verdicts.REJECT


def empty_payload(payload, schema, r):
    payload.clear()
    return verdicts.REJECT if _required(schema) else verdicts.ANY


def junk_keys(payload, schema, r):
    """Campos desconhecidos: o DRF ignora. Aqui so nao pode quebrar."""
    for i in range(r.randint(5, 60)):
        payload[f"campo_inventado_{i}"] = r.choice([1, "x", None, [1, 2], {"a": 1}])
    return verdicts.ACCEPT


def injection(payload, schema, r):
    """Texto hostil precisa ser ARMAZENADO em seguranca, nao recusado."""
    alvos = [f for f, meta in schema.fields.items() if meta.get("type") == "string" and f in payload]
    if not alvos:
        return None
    payload[r.choice(alvos)] = r.choice([
        "'; DROP TABLE orders; --",
        "<script>fetch('/api/v1/users/')</script>",
        "{{7*7}}",
        "../../../../etc/passwd",
        " byte nulo",
    ])
    return verdicts.ANY


def deep_nesting(payload, schema, r):
    alvos = [f for f, meta in schema.fields.items() if meta.get("type") in ("object", None)]
    payload[r.choice(alvos) if alvos else "metadata"] = DEEP
    return verdicts.ANY


MUTATIONS = [
    ("faltando_obrigatorio", drop_required),
    ("nulo_em_obrigatorio", null_required),
    ("tipo_errado", wrong_type),
    ("texto_gigante", too_long),
    ("enum_invalido", bad_enum),
    ("valor_negativo", negative_money),
    ("referencia_quebrada", broken_reference),
    ("numero_absurdo", huge_number),
    ("nao_numero", not_a_number),
    ("payload_vazio", empty_payload),
    ("campos_desconhecidos", junk_keys),
    ("texto_hostil", injection),
    ("json_profundo", deep_nesting),
]

RAW_CASES = [
    ("json_malformado", b'{"name": "sem fechar"', "application/json", verdicts.REJECT),
    ("json_array", b"[1,2,3]", "application/json", verdicts.REJECT),
    ("corpo_vazio", b"", "application/json", verdicts.REJECT),
    ("content_type_errado", b"name=teste&price=10", "application/x-www-form-urlencoded", verdicts.ANY),
    ("texto_puro", b"isso nao e json", "text/plain", verdicts.REJECT),
    ("corpo_gigante", b'{"name": "' + b"A" * 2_000_000 + b'"}', "application/json", verdicts.REJECT),
    ("bytes_binarios", bytes(range(256)) * 8, "application/json", verdicts.REJECT),
]


def apply_mutation(payload, schema, r):
    """Escolhe e aplica uma mutacao; devolve (caso, expectativa)."""
    for _ in range(4):
        case, mutate = r.choice(MUTATIONS)
        copia = json.loads(json.dumps(payload, default=str))
        expectation = mutate(copia, schema, r)
        if expectation is not None:
            payload.clear()
            payload.update(copia)
            return case, expectation
    return "campos_desconhecidos", junk_keys(payload, schema, r)
