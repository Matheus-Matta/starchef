"""A venda completa como o PDV faz: abre, lanca, manda pra cozinha, fecha, recebe.

Cada etapa vira uma `Operation` — assim o mesmo codigo serve para o terminal
online (entrega na hora) e para o offline (enfileira e sobe depois), que e
exatamente a promessa do PDV offline-first.
"""
from decimal import Decimal

from .. import result as verdicts
from .outbox import Operation


def _preco(produto):
    try:
        return Decimal(str(produto.get("price") or "0"))
    except (TypeError, ValueError):
        return Decimal("0")


def abrir_pedido(terminal, refs, rng):
    """Comanda quando existe; senao balcao. Devolve (operacao, referencia)."""
    if refs.command_codes and rng.random() < 0.7:
        comanda = rng.choice(refs.ids["commands"])
        operacao = Operation(
            "POST", "/api/v1/orders/open-command/", {"command": comanda},
            kind="abrir_pedido", local_id=terminal.local_id(),
        )
    else:
        operacao = Operation(
            "POST", "/api/v1/orders/",
            {"order_type": "counter", "restaurant": str((refs.restaurant or {}).get("id", ""))},
            kind="abrir_pedido", local_id=terminal.local_id(),
        )
    return operacao


def _item_valido(refs, rng):
    produto = rng.choice(refs.unit_products) if refs.unit_products else None
    if produto is None:
        return None, Decimal("0")
    quantidade = rng.choice([1, 1, 1, 2, 3])
    corpo = {"product": str(produto["id"]), "quantity": quantidade}
    if rng.random() < 0.4:
        corpo["expected_unit_price"] = str(_preco(produto))
    if rng.random() < 0.25:
        corpo["customer_note"] = rng.choice(["sem cebola", "bem passado", "  ", "PRA VIAGEM!!!"])
    return corpo, _preco(produto) * quantidade


ITEM_CHAOS = [
    ("item_sem_produto", lambda corpo, rng: corpo.pop("product", None)),
    ("quantidade_zero", lambda corpo, rng: corpo.update({"quantity": 0})),
    ("quantidade_negativa", lambda corpo, rng: corpo.update({"quantity": -3})),
    ("quantidade_texto", lambda corpo, rng: corpo.update({"quantity": "duas"})),
    ("produto_inexistente", lambda corpo, rng: corpo.update({"product": "11111111-2222-3333-4444-555555555555"})),
    ("produto_nao_uuid", lambda corpo, rng: corpo.update({"product": "produto-errado"})),
    ("preco_esperado_errado", lambda corpo, rng: corpo.update({"expected_unit_price": "0.01"})),
]


def itens(terminal, refs, rng, order_ref, chaos_ratio):
    """De 1 a 5 itens; parte deles com o preenchimento errado de um operador real."""
    operacoes, total = [], Decimal("0")
    for _ in range(rng.randint(1, 5)):
        corpo, valor = _item_valido(refs, rng)
        if corpo is None:
            continue
        expectativa, caso = verdicts.ACCEPT, "valido"
        if rng.random() < chaos_ratio:
            caso, estragar = rng.choice(ITEM_CHAOS)
            estragar(corpo, rng)
            expectativa = verdicts.ACCEPT if caso == "preco_esperado_errado" else verdicts.REJECT
        else:
            total += valor
        operacoes.append(Operation(
            "POST", f"/api/v1/orders/{order_ref}/items/", corpo,
            kind="lancar_item", expectation=expectativa, case=caso,
        ))
    return operacoes, total


def enviar_cozinha(terminal, order_ref, rng, offline):
    corpo = {"client_batch_serial": rng.randint(1, 999999)}
    if offline:
        # O terminal reivindicou a impressao antes de imprimir (§ comanda de cozinha).
        corpo["offline_printed"] = True
    return Operation(
        "POST", f"/api/v1/orders/{order_ref}/send-to-kitchen/", corpo,
        kind="enviar_cozinha", barrier=True,
    )


def fechar(terminal, order_ref, total, rng, chaos_ratio):
    corpo = {"discount": 0, "service_fee_enabled": rng.random() < 0.6}
    caso, expectativa = "valido", verdicts.ACCEPT
    sorteio = rng.random()
    if sorteio < 0.45:
        corpo["expected_total"] = str(total)
    elif sorteio < 0.65:
        # Divergencia proposital: o servidor deve concluir com o total dele.
        corpo["expected_total"] = str(total + Decimal("13.37"))
        caso = "total_divergente"
    if rng.random() < chaos_ratio:
        caso, expectativa = rng.choice([
            ("desconto_negativo", verdicts.REJECT),
            ("desconto_maior_que_total", verdicts.REJECT),
            ("desconto_texto", verdicts.REJECT),
        ])
        corpo["discount"] = {"desconto_negativo": -50, "desconto_maior_que_total": 999999,
                             "desconto_texto": "dez reais"}[caso]
    return Operation(
        "POST", f"/api/v1/orders/{order_ref}/close/", corpo,
        kind="fechar_pedido", barrier=True, expectation=expectativa, case=caso,
    )


PAY_CHAOS = [
    ("pagamento_sem_valor", verdicts.REJECT),
    ("pagamento_sem_forma", verdicts.REJECT),
    ("valor_texto", verdicts.REJECT),
    ("valor_negativo", verdicts.REJECT),
    ("cartao_sem_subtipo", verdicts.REJECT),
    ("forma_inexistente", verdicts.REJECT),
]


def receber(terminal, refs, order_ref, total, rng, chaos_ratio):
    metodos = list(refs.payment_by_type.values())
    if not metodos:
        return None
    metodo = rng.choice(metodos)
    corpo = {"payment_method": str(metodo["id"]), "amount": str(total if total > 0 else Decimal("10.00"))}
    if metodo.get("method_type") == "card":
        corpo["card_subtype"] = rng.choice(["debit", "credit"])
    if metodo.get("method_type") == "cash" and terminal.cash_register:
        corpo["cash_register"] = terminal.cash_register
        if rng.random() < 0.3:
            corpo["amount"] = str(total + Decimal("20.00"))  # troco
    caso, expectativa = "valido", verdicts.ACCEPT
    if rng.random() < chaos_ratio:
        caso, expectativa = rng.choice(PAY_CHAOS)
        if caso == "pagamento_sem_valor":
            corpo.pop("amount", None)
        elif caso == "pagamento_sem_forma":
            corpo.pop("payment_method", None)
        elif caso == "valor_texto":
            corpo["amount"] = "vinte reais"
        elif caso == "valor_negativo":
            corpo["amount"] = "-99.90"
        elif caso == "cartao_sem_subtipo":
            corpo["payment_method"] = str(
                (refs.payment_by_type.get("card") or metodo)["id"]
            )
            corpo.pop("card_subtype", None)
        elif caso == "forma_inexistente":
            corpo["payment_method"] = "99999999-8888-7777-6666-555555555555"
    return Operation(
        "POST", f"/api/v1/orders/{order_ref}/pay/", corpo,
        kind="receber", barrier=True, expectation=expectativa, case=caso,
    )
