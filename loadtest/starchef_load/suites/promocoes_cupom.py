"""As fases de CUPOM da suíte `promocoes`: onde a corrida custa dinheiro.

Separadas do preço porque a natureza do defeito é outra. No preço, a corrida
produz uma LEITURA errada — ruim, e visível. No cupom, ela produz um DESCONTO a
mais: dinheiro que saiu, num registro que parece perfeitamente normal depois.

O resgate nasce no PAGAMENTO, e entre conferir o limite e gravar o resgate existe
uma janela. Duas vendas simultâneas com o mesmo cupom e o mesmo CPF é o que um
script de fraude faz de propósito — e o que um sábado de movimento faz por
acidente, com dois caixas cobrando ao mesmo tempo.
"""
import threading
import time
import uuid
from decimal import Decimal

from ..auth import clone
from ..workers import LoadRunner

# CPFs válidos (dígito verificador confere) e distintos: o backend recusa CPF
# inválido, e a recusa apareceria como "o cupom foi barrado" quando o que houve
# foi o CPF.
CPF_UNICO = "39053344705"
CPF_OUTRO = "11144477735"


def _s(ctx):
    """O módulo irmão, importado tarde para não fechar ciclo entre os dois."""
    from . import promocoes

    return promocoes


def _abrir_caixa(ctx, refs):
    """Sem caixa aberto o pagamento é recusado — e o resgate nunca nasce.

    A fase inteira mediria a ausência de caixa, e reprovaria o cupom por uma
    pré-condição de cadastro.
    """
    p = _s(ctx)
    atual = ctx.session.get("/api/v1/cash-register/current/")
    if atual.status == 200 and (atual.json() or {}).get("id"):
        return True
    lista = ctx.session.get("/api/v1/cash-stations/?page_size=50&is_active=true")
    corpo = lista.json() or {}
    usuario = (ctx.session.user or {}).get("id")
    for estacao in (corpo.get("results") or corpo.get("data") or []):
        for tentativa in (1, 2):
            resposta = p.chamar(ctx, ctx.session, "abrir_caixa", "POST",
                                "/api/v1/cash-register/open/",
                                "/api/v1/cash-register/open/",
                                {"cash_station": estacao.get("id"),
                                 "opening_amount": "500.00", "notes": "carga promocoes"})
            if resposta.status in (200, 201, 409):
                return True
            if tentativa == 1 and usuario and "vinculado" in p.motivo(resposta).lower():
                ctx.session.patch(f"/api/v1/cash-stations/{estacao.get('id')}/",
                                  {"operators": [usuario]})
                continue
            break
    return False


def _criar_cupom(ctx, corpo):
    p = _s(ctx)
    resposta = p.chamar(ctx, ctx.session, "criar_cupom", "POST",
                        "/api/v1/promotions/coupons/",
                        "/api/v1/promotions/coupons/", corpo)
    if resposta.status not in (200, 201):
        return None, f"HTTP {resposta.status}: {p.motivo(resposta)}"
    return (resposta.json() or {}).get("id"), ""


def _vender_com_cupom(ctx, sessao, refs, cenario, codigo, cpf):
    """Abre, fecha com o cupom e paga. Devolve `(ok, desconto, motivo)`.

    O cupom sobe NO FECHAMENTO, junto do CPF, porque é assim que o caixa faz: o
    CPF é a identidade do cupom, e aplicá-lo antes de gravar o CPF recusaria quem
    acabou de informá-lo.
    """
    p = _s(ctx)
    restaurante = str((refs.restaurant or {}).get("id", ""))
    abertura = p.chamar(ctx, sessao, "abrir_conta", "POST", "/api/v1/orders/",
                        "/api/v1/orders/",
                        {"order_type": "counter", "restaurant": restaurante})
    if abertura.status not in (200, 201):
        return False, None, f"abrir HTTP {abertura.status}: {p.motivo(abertura)}"
    pedido = (abertura.json() or {}).get("id")
    if not pedido:
        return False, None, "a abertura não devolveu id"

    item = p.chamar(ctx, sessao, "lancar_item", "POST",
                    f"/api/v1/orders/{pedido}/items/",
                    "/api/v1/orders/{id}/items/",
                    {"product": cenario["produto"], "quantity": 4,
                     "variations": [], "addons": [], "customer_note": ""})
    if item.status not in (200, 201):
        return False, None, f"lançar HTTP {item.status}: {p.motivo(item)}"

    fechamento = p.chamar(ctx, sessao, "fechar_com_cupom", "POST",
                          f"/api/v1/orders/{pedido}/close/",
                          "/api/v1/orders/{id}/close/",
                          {"discount": 0, "service_fee_enabled": False,
                           "fiscal_customer_cpf": cpf, "coupon_code": codigo},
                          esperado="2xx|422")
    if fechamento.status == 422:
        # 422 `coupon_rejected` é o resultado CERTO para quem perdeu a corrida.
        return False, None, p.motivo(fechamento)
    if fechamento.status not in (200, 201):
        return False, None, f"fechar HTTP {fechamento.status}: {p.motivo(fechamento)}"

    corpo = fechamento.json() or {}
    desconto = p.dinheiro(corpo.get("coupon_discount")) or Decimal("0")
    total = corpo.get("total") or "0"
    metodo = (refs.payment_by_type.get("cash") or {}).get("id")
    if not metodo:
        return False, desconto, "cenário sem forma de pagamento em dinheiro"
    pagamento = p.chamar(ctx, sessao, "pagar", "POST",
                         f"/api/v1/orders/{pedido}/pay/",
                         "/api/v1/orders/{id}/pay/",
                         {"payment_method": metodo, "amount": str(total)})
    if pagamento.status not in (200, 201):
        return False, desconto, f"pagar HTTP {pagamento.status}: {p.motivo(pagamento)}"
    return True, desconto, ""


def _resgates(ctx, cupom):
    """Quantas vezes o cupom foi resgatado, segundo o servidor."""
    p = _s(ctx)
    resposta = p.chamar(ctx, ctx.session, "listar_resgates", "GET",
                        f"/api/v1/promotions/coupons/{cupom}/redemptions/?page_size=200",
                        "/api/v1/promotions/coupons/{id}/redemptions/")
    if resposta.status != 200:
        return None
    corpo = resposta.json() or {}
    linhas = corpo.get("results") if isinstance(corpo, dict) else corpo
    if linhas is None:
        linhas = (corpo.get("data") or []) if isinstance(corpo, dict) else []
    return len(linhas)


# ──────────────────────────────────── fase 3: compra única por cliente

def fase_compra_unica(ctx, refs, cenario):
    """O MESMO CPF tentando o MESMO cupom de uso único, em paralelo.

    Exatamente uma venda pode levar o desconto. Duas significam desconto dado
    duas vezes para quem tinha direito a uma — e o registro fica parecendo normal
    nas duas vendas, então ninguém descobre depois.
    """
    p = _s(ctx)
    ctx.log(f"[{p.SUITE}] fase 3/6 — compra única por cliente, em corrida")
    if not _abrir_caixa(ctx, refs):
        ctx.check(p.SUITE, "há caixa aberto para cobrar", False,
                  "nenhuma estação aceitou abrir — as fases de cupom não rodam")
        return

    codigo = f"LTUNICO{cenario['sufixo'].upper()}"
    cupom, erro = _criar_cupom(ctx, {
        "code": codigo, "discount_kind": "amount", "discount_value": "5.00",
        "single_use_per_customer": True, "requires_document": True,
    })
    if not cupom:
        ctx.check(p.SUITE, "o cupom de uso único foi criado", False, erro)
        return

    vencedores = []
    perdedores = []
    trava = threading.Lock()
    # Poucos trabalhadores e MUITA simultaneidade: o que abre a janela é a
    # largada junta, não o volume. Trinta tentativas espaçadas não disputam nada.
    largada = threading.Barrier(6, timeout=30)

    def tentar(worker, _iteracao):
        sessao = clone(ctx.session, terminal_name=f"LT-CUPOM-{worker + 1}")
        try:
            largada.wait()
        except threading.BrokenBarrierError:
            pass
        ok, desconto, razao = _vender_com_cupom(ctx, sessao, refs, cenario, codigo, CPF_UNICO)
        with trava:
            if ok and desconto and desconto > 0:
                vencedores.append(desconto)
            else:
                perdedores.append(razao)

    LoadRunner(workers=6, count=6).run(tentar)

    gravados = _resgates(ctx, cupom)
    ctx.check(p.SUITE, "só UMA venda leva o cupom de uso único",
              len(vencedores) == 1,
              f"{len(vencedores)} venda(s) receberam o desconto "
              f"(esperado 1); recusas: {sorted(set(perdedores))[:3]}")
    if gravados is not None:
        ctx.check(p.SUITE, "o servidor registrou um resgate só",
                  gravados == 1,
                  f"{gravados} resgate(s) gravados para o mesmo CPF")

    # Outro CPF continua com direito: o limite é por pessoa, e um bloqueio global
    # seria outro defeito — o segundo cliente perderia um cupom que é dele.
    sessao = clone(ctx.session, terminal_name="LT-CUPOM-OUTRO")
    ok, desconto, razao = _vender_com_cupom(ctx, sessao, refs, cenario, codigo, CPF_OUTRO)
    ctx.check(p.SUITE, "outro CPF ainda tem direito ao mesmo cupom",
              bool(ok and desconto and desconto > 0), razao)


# ──────────────────────────────────── fase 4: limite total de usos

def fase_limite_total(ctx, refs, cenario):
    """Cupom com teto de usos, e mais gente tentando do que o teto permite.

    O teto é do RESTAURANTE, não do cliente: "as primeiras 2 vendas". Se ele
    vazar sob corrida, o restaurante deu mais desconto do que aprovou.
    """
    p = _s(ctx)
    ctx.log(f"[{p.SUITE}] fase 4/6 — teto de usos sob corrida")
    teto = 2
    tentativas = 6
    codigo = f"LTTETO{cenario['sufixo'].upper()}"
    cupom, erro = _criar_cupom(ctx, {
        "code": codigo, "discount_kind": "amount", "discount_value": "3.00",
        "usage_limit": teto,
    })
    if not cupom:
        ctx.check(p.SUITE, "o cupom com teto foi criado", False, erro)
        return

    ganhos = []
    trava = threading.Lock()
    largada = threading.Barrier(tentativas, timeout=30)

    def tentar(worker, _iteracao):
        sessao = clone(ctx.session, terminal_name=f"LT-TETO-{worker + 1}")
        try:
            largada.wait()
        except threading.BrokenBarrierError:
            pass
        # CPF por trabalhador: o limite aqui é TOTAL, e repetir o CPF misturaria
        # esta medição com a do limite por cliente.
        ok, desconto, _razao = _vender_com_cupom(
            ctx, sessao, refs, cenario, codigo, "")
        if ok and desconto and desconto > 0:
            with trava:
                ganhos.append(desconto)

    LoadRunner(workers=tentativas, count=tentativas).run(tentar)

    gravados = _resgates(ctx, cupom)
    ctx.check(p.SUITE, f"o teto de {teto} usos não vaza sob corrida",
              len(ganhos) <= teto,
              f"{len(ganhos)} vendas levaram o desconto de um cupom limitado a {teto}")
    if gravados is not None:
        ctx.check(p.SUITE, "os resgates gravados respeitam o teto",
                  gravados <= teto, f"{gravados} resgates para um teto de {teto}")


# ──────────────────────────────────── fase 5: cupom na tela de pagamento

def fase_cupom_no_pagamento(ctx, refs, cenario):
    """Aplicar, trocar e retirar o cupom com a conta já fechada.

    A guarda que interessa é uma: o total nunca pode cair abaixo do que já foi
    recebido. Se cair, o caixa fica devendo um troco que nenhum recebimento
    registrou — e a diferença só aparece na conferência da gaveta.
    """
    p = _s(ctx)
    ctx.log(f"[{p.SUITE}] fase 5/6 — aplicar, trocar e retirar no pagamento")
    codigo = f"LTPAGO{cenario['sufixo'].upper()}"
    cupom, erro = _criar_cupom(ctx, {
        "code": codigo, "discount_kind": "amount", "discount_value": "2.00",
    })
    if not cupom:
        ctx.check(p.SUITE, "o cupom do pagamento foi criado", False, erro)
        return

    abaixo_do_recebido = []
    trava = threading.Lock()

    def mexer(worker, _iteracao):
        sessao = clone(ctx.session, terminal_name=f"LT-PGCUPOM-{worker + 1}")
        restaurante = str((refs.restaurant or {}).get("id", ""))
        abertura = p.chamar(ctx, sessao, "abrir_conta", "POST", "/api/v1/orders/",
                            "/api/v1/orders/",
                            {"order_type": "counter", "restaurant": restaurante})
        if abertura.status not in (200, 201):
            return
        pedido = (abertura.json() or {}).get("id")
        p.chamar(ctx, sessao, "lancar_item", "POST",
                 f"/api/v1/orders/{pedido}/items/",
                 "/api/v1/orders/{id}/items/",
                 {"product": cenario["produto"], "quantity": 3,
                  "variations": [], "addons": [], "customer_note": ""})
        fechamento = p.chamar(ctx, sessao, "fechar_conta", "POST",
                              f"/api/v1/orders/{pedido}/close/",
                              "/api/v1/orders/{id}/close/",
                              {"discount": 0, "service_fee_enabled": False})
        if fechamento.status not in (200, 201):
            return
        total = p.dinheiro((fechamento.json() or {}).get("total")) or Decimal("0")

        metodo = (refs.payment_by_type.get("cash") or {}).get("id")
        # Paga METADE: sobra saldo, e é nesse estado que aplicar cupom é legítimo
        # — a guarda só barra quando o desconto passaria do que já entrou.
        parcial = (total / 2).quantize(Decimal("0.01"))
        if metodo and parcial > 0:
            p.chamar(ctx, sessao, "pagar_parcial", "POST",
                     f"/api/v1/orders/{pedido}/pay/",
                     "/api/v1/orders/{id}/pay/",
                     {"payment_method": metodo, "amount": str(parcial)})

        for acao, valor in (("aplicar", codigo), ("retirar", ""), ("aplicar", codigo)):
            resposta = p.chamar(ctx, sessao, f"cupom_{acao}", "POST",
                                f"/api/v1/orders/{pedido}/apply-coupon/",
                                "/api/v1/orders/{id}/apply-coupon/",
                                {"code": valor}, esperado="2xx|422")
            if resposta.status not in (200, 201):
                continue
            corpo = resposta.json() or {}
            novo_total = p.dinheiro(corpo.get("total"))
            if novo_total is not None and novo_total < parcial:
                with trava:
                    abaixo_do_recebido.append(
                        f"total {novo_total} < recebido {parcial}")

    LoadRunner(workers=max(4, ctx.config.workers // 4), rate=ctx.config.rate,
               duration=max(3.0, ctx.config.duration / 4)).run(mexer)

    ctx.check(p.SUITE, "o cupom nunca derruba o total abaixo do recebido",
              not abaixo_do_recebido,
              "; ".join(sorted(set(abaixo_do_recebido))[:4]))
