"""O turno do PDV desktop pelo caminho de hoje: a venda inteira em `/orders/submit/`.

O app abre o pagamento SIMULANDO (`simular: true`, nada gravado) e conclui
com tudo num envio só: itens, fechamento, recebimentos e a cozinha
(`OrderDraftMaterializer` em `pdv_desktop/lib`). A suíte antiga fazia abrir,
lançar, cozinha, fechar e pagar, uma rota por gesto — um caminho que o app
não percorre mais.

Cada venda sorteia um cenário, e cada cenário tem o seu grupo no relatório
(p50/p95/p99 e 409 por grupo):

* `simples`         — 1 a 3 itens, dinheiro;
* `cupom_valido`    — o cupom da carga no fechamento: o desconto TEM de vir;
* `cupom_recusado`  — um código que não existe: a simulação TEM de recusar
  (4xx), e a venda segue sem ele, como o caixa faria;
* `dividido`        — dois recebimentos que somam o total.

Vários terminais ao mesmo tempo é o `--workers`: cada trabalhador é um PDV.
"""
import time
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

SUITE = "desktop"
ROTA = "/api/v1/orders/submit/"
CENARIOS = ("simples", "cupom_valido", "cupom_recusado", "dividido")
CUPOM_INEXISTENTE = "LTNAOEXISTE"


def criar_cupom(ctx):
    """O cupom válido da carga, sem limite de uso: o que se mede é o cálculo."""
    codigo = f"LTDESK{uuid.uuid4().hex[:6].upper()}"
    resposta = ctx.session.post("/api/v1/promotions/coupons/", {
        "code": codigo, "name": "Carga do desktop", "discount_kind": "amount",
        "discount_value": "1.00",
    })
    if resposta.status not in (200, 201):
        ctx.note(SUITE, f"cupom da carga não criado (HTTP {resposta.status}); "
                        "cenário cupom_valido vira simples")
        return None
    return codigo


def _agora():
    return datetime.now(timezone.utc).isoformat()


def _pagamento(metodo, valor, subtipo=""):
    corpo = {"id": str(uuid.uuid4()), "payment_method": metodo, "amount": str(valor),
             "client_updated_at": _agora()}
    if subtipo:
        # Cartão sem "crédito" ou "débito" é recusado (400), como no PDV.
        corpo["card_subtype"] = subtipo
    return corpo


def _enviar(ctx, sessao, cenario, etapa, corpo, *, esperado="2xx"):
    inicio = time.time()
    resposta = sessao.post(ROTA, corpo, idempotency_key=str(uuid.uuid4()))
    ctx.record(SUITE, f"{SUITE}::{etapa}_{cenario}", "POST", ROTA, resposta,
               expectation=esperado, started=inicio)
    return resposta


def uma_venda(ctx, sessao, refs, rng, cupom):
    """Simula e conclui uma venda. Devolve o resumo, ou None se não fechou."""
    cenario = rng.choice(CENARIOS)
    if cenario == "cupom_valido" and not cupom:
        cenario = "simples"
    dinheiro = (refs.payment_by_type.get("cash") or {}).get("id")
    if not refs.unit_products or not dinheiro:
        return None
    restaurante = str((refs.restaurant or {}).get("id", ""))
    itens = [{"id": str(uuid.uuid4()), "product": rng.choice(refs.unit_products).get("id"),
              "quantity": 1} for _ in range(rng.randint(1, 3))]
    fechamento = {"discount": 0, "service_fee_enabled": False}
    if cenario == "cupom_valido":
        fechamento["coupon_code"] = cupom
    corpo = {"id": str(uuid.uuid4()), "order_type": "counter", "restaurant": restaurante,
             "items": itens, "close": fechamento}

    if cenario == "cupom_recusado":
        recusa = _enviar(ctx, sessao, cenario, "simular",
                         {**corpo, "simular": True, "payments": [],
                          "close": {**fechamento, "coupon_code": CUPOM_INEXISTENTE}},
                         esperado="reject")
        if not 400 <= recusa.status < 500:
            return {"cenario": cenario, "recusa_errada": recusa.status}

    previa = _enviar(ctx, sessao, cenario, "simular", {**corpo, "simular": True, "payments": []})
    if previa.status not in (200, 201):
        return None
    pedido = (previa.json() or {}).get("order") or {}
    total = Decimal(str(pedido.get("total") or "0"))
    if cenario == "cupom_valido" and Decimal(str(pedido.get("coupon_discount") or "0")) <= 0:
        return {"cenario": cenario, "sem_desconto": True}

    if cenario == "dividido" and total >= Decimal("0.02"):
        tipo, outro = next(((t, m.get("id")) for t, m in refs.payment_by_type.items()
                            if t != "cash" and m), ("cash", dinheiro))
        metade = (total / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        subtipo = "credit" if "card" in tipo else ""
        pagamentos = [_pagamento(dinheiro, metade), _pagamento(outro, total - metade, subtipo)]
    else:
        pagamentos = [_pagamento(dinheiro, total)]

    concluida = _enviar(ctx, sessao, cenario, "concluir", {
        **corpo, "payments": pagamentos, "expected_total": str(total),
        "kitchen": {"client_batch_serial": uuid.uuid4().hex[:12]},
    })
    if concluida.status not in (200, 201):
        return None
    final = (concluida.json() or {}).get("order") or {}
    return {"cenario": cenario, "pedido": final.get("id") or corpo["id"], "valor": total,
            "recebimentos": len(pagamentos)}


def conferir_cenarios(ctx, resultados):
    """O que o turno prova além de vazão: cupom calculado e recusado direito."""
    sem_desconto = sum(1 for r in resultados if r.get("sem_desconto"))
    recusas_erradas = [r["recusa_errada"] for r in resultados if "recusa_errada" in r]
    por_cenario = {c: sum(1 for r in resultados if r.get("cenario") == c and r.get("pedido"))
                   for c in CENARIOS}
    ctx.note(SUITE, "vendas por cenário: " + ", ".join(f"{c}={n}" for c, n in por_cenario.items()))
    conflitos = sum(
        stats.statuses.get(409, 0) for chave, stats in ctx.recorder.groups.items()
        if chave.startswith(f"{SUITE}::{SUITE}::simular") or chave.startswith(f"{SUITE}::{SUITE}::concluir")
    )
    ctx.note(SUITE, f"409 no turno (simular + concluir): {conflitos}")
    ctx.check(SUITE, "o cupom válido sempre dá desconto", sem_desconto == 0,
              f"{sem_desconto} venda(s) com o cupom da carga e desconto zero")
    ctx.check(SUITE, "o cupom inexistente é recusado com 4xx", not recusas_erradas,
              f"respostas fora de 4xx: {sorted(set(recusas_erradas))}")
