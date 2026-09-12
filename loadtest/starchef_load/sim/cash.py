"""Turno de caixa e venda pela Balanca Rapida.

Sao os dois fluxos que o desktop tem e a web nao: a gaveta (abertura, sangria,
suprimento, fechamento com diferenca) e a pesagem hands-free, que no PDV tem
duas rotas — online com `ScaleReading` e offline com o peso bruto no corpo.
"""
from decimal import Decimal

from .. import result as verdicts
from .outbox import Operation


def abrir_caixa(terminal, refs, rng):
    estacao = refs.cash_station
    if not estacao:
        return None
    corpo = {
        "cash_station": str(estacao["id"]),
        "opening_amount": str(rng.choice([0, 50, 100, 200, "150.50"])),
        "station": terminal.name,
        "terminal_role": terminal.role,
        "terminal_name": terminal.name,
    }
    return Operation("POST", "/api/v1/cash-register/open/", corpo, kind="abrir_caixa", barrier=True)


MOVIMENTO_CHAOS = [
    ("sangria_sem_valor", verdicts.REJECT),
    ("sangria_negativa", verdicts.REJECT),
    ("sangria_texto", verdicts.REJECT),
    ("sangria_maior_que_o_caixa", verdicts.ANY),
]


def movimento(terminal, rng, chaos_ratio):
    if not terminal.cash_register:
        return None
    tipo = rng.choice(["withdrawal", "supply"])
    corpo = {"amount": str(round(rng.uniform(5, 120), 2)), "reason": rng.choice(["troco", "deposito", "", "sangria"])}
    corpo["destination" if tipo == "withdrawal" else "source"] = rng.choice(["cofre", "gerente", ""])
    caso, expectativa = "valido", verdicts.ACCEPT
    if rng.random() < chaos_ratio:
        caso, expectativa = rng.choice(MOVIMENTO_CHAOS)
        if caso == "sangria_sem_valor":
            corpo.pop("amount")
        elif caso == "sangria_negativa":
            corpo["amount"] = "-500"
        elif caso == "sangria_texto":
            corpo["amount"] = "cem reais"
        else:
            corpo["amount"] = "999999.99"
    return Operation(
        "POST", f"/api/v1/cash-register/{terminal.cash_register}/{tipo}/", corpo,
        kind=f"caixa_{tipo}", expectation=expectativa, case=caso,
    )


def fechar_caixa(terminal, rng, chaos_ratio):
    if not terminal.cash_register:
        return None
    corpo = {"actual_amount": str(round(rng.uniform(50, 900), 2)), "notes": rng.choice(["", "conferido", "faltou troco"])}
    caso, expectativa = "valido", verdicts.ACCEPT
    if rng.random() < chaos_ratio:
        caso, expectativa = rng.choice([
            ("fechamento_sem_valor", verdicts.REJECT),
            ("fechamento_texto", verdicts.REJECT),
            ("fechamento_negativo", verdicts.REJECT),
        ])
        if caso == "fechamento_sem_valor":
            corpo.pop("actual_amount")
        elif caso == "fechamento_texto":
            corpo["actual_amount"] = "uns quinhentos"
        else:
            corpo["actual_amount"] = "-10"
    return Operation(
        "POST", f"/api/v1/cash-register/{terminal.cash_register}/close/", corpo,
        kind="fechar_caixa", barrier=True, expectation=expectativa, case=caso,
    )


def leitura_de_peso(refs, rng, chaos_ratio):
    """`POST /scales/readings/` — a leitura fisica, que so existe online."""
    if not refs.scale:
        return None
    corpo = {
        "scale": str(refs.scale["id"]),
        "weight_kg": str(rng.choice([0.35, 0.480, 1.2, 0.075, 2.5])),
        "tare_kg": str(rng.choice([0, 0, 0.02])),
        "is_stable": True,
        "source": rng.choice(["agent", "manual"]),
    }
    caso, expectativa = "valido", verdicts.ACCEPT
    if rng.random() < chaos_ratio:
        caso, expectativa = rng.choice([
            ("peso_zero", verdicts.REJECT),
            ("peso_negativo", verdicts.REJECT),
            ("peso_texto", verdicts.REJECT),
            ("tara_maior_que_peso", verdicts.REJECT),
            ("balanca_inexistente", verdicts.REJECT),
        ])
        if caso == "peso_zero":
            corpo["weight_kg"] = "0"
        elif caso == "peso_negativo":
            corpo["weight_kg"] = "-1.5"
        elif caso == "peso_texto":
            corpo["weight_kg"] = "meio quilo"
        elif caso == "tara_maior_que_peso":
            corpo["tare_kg"] = "99"
        else:
            corpo["scale"] = "12345678-1234-1234-1234-123456789012"
    return Operation("POST", "/api/v1/scales/readings/", corpo, kind="leitura_balanca",
                     expectation=expectativa, case=caso)


def checkout_balanca(refs, rng, *, reading_id=None, peso_bruto=None, chaos_ratio=0.0):
    """Fecha a pesagem na comanda. Sem `reading_id`, e o replay offline por peso."""
    if not refs.scale or not refs.command_codes:
        return None
    corpo = {"command_code": rng.choice(refs.command_codes)}
    if reading_id:
        corpo["scale_reading"] = reading_id
    else:
        corpo["weight_kg"] = str(peso_bruto or round(rng.uniform(0.1, 2.0), 3))
    if refs.unit_products and rng.random() < 0.4:
        corpo["extras"] = [
            {"product": str(rng.choice(refs.unit_products)["id"]), "quantity": rng.choice([1, 2])}
            for _ in range(rng.randint(1, 3))
        ]
    caso, expectativa = "valido", verdicts.ACCEPT
    if rng.random() < chaos_ratio:
        caso, expectativa = rng.choice([
            ("comanda_inexistente", verdicts.REJECT),
            ("comanda_vazia", verdicts.REJECT),
            ("sem_peso_nem_leitura", verdicts.REJECT),
            ("extras_demais", verdicts.REJECT),
            ("extra_sem_produto", verdicts.REJECT),
        ])
        if caso == "comanda_inexistente":
            corpo["command_code"] = "COMANDA-QUE-NAO-EXISTE"
        elif caso == "comanda_vazia":
            corpo["command_code"] = ""
        elif caso == "sem_peso_nem_leitura":
            corpo.pop("scale_reading", None)
            corpo.pop("weight_kg", None)
        elif caso == "extras_demais":
            corpo["extras"] = [{"product": str(refs.ids["products"][0]), "quantity": 1}] * 40
        else:
            corpo["extras"] = [{"quantity": 2}]
    return Operation(
        "POST", f"/api/v1/scales/{refs.scale['id']}/checkout-command/", corpo,
        kind="checkout_balanca", barrier=True, expectation=expectativa, case=caso,
    )


def total_esperado(refs, quantidade_itens):
    """Estimativa de total usada quando o terminal esta offline."""
    if not refs.unit_products:
        return Decimal("0")
    preco = Decimal(str(refs.unit_products[0].get("price") or "0"))
    return preco * quantidade_itens
