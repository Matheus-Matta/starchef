"""Suite PROMOCOES — preço dinâmico, cupom e código do operador sob corrida.

O que esta suíte ataca não é "o desconto sai certo" — isso o teste de unidade já
fixa. É o que só a CONCORRÊNCIA quebra, e são três perguntas:

    1. **o preço que a vitrine mostra é sempre um preço que existe?** O preço
       virou cálculo: `current_price` resolve a disputa entre tabelas de desconto
       a cada leitura. Trinta caixas lendo o catálogo enquanto alguém liga e
       desliga uma tabela é onde um cache errado ou uma resolução parcial
       apareceria — como um terceiro valor que não é nem o de prateleira nem o da
       promoção.

    2. **"compra única por cliente" resiste a duas vendas simultâneas?** Esta é a
       pergunta caríssima. O resgate nasce no pagamento, e entre conferir o
       limite e gravar o resgate existe uma janela. Dois caixas pagando ao mesmo
       tempo com o mesmo CPF e o mesmo cupom é exatamente o que um script de
       fraude faz — e o que um dia de movimento faz por acidente.

    3. **o código do operador é exigido SEMPRE?** Uma exigência que vale em 99%
       das requisições é uma exigência que não vale: o 1% que passa é o
       lançamento sem rastro, e é nele que a conferência do restaurante vai bater.

O preparo cria cadastro próprio (tabela, regras, cupons) com nomes marcados, para
não depender de o cenário ter promoção nenhuma e para não sujar o que já existe.
"""
import threading
import time
import uuid
from decimal import Decimal, InvalidOperation

from ..auth import clone
from ..workers import LoadRunner
from . import promocoes_cupom, promocoes_operador

SUITE = "promocoes"

#: Marca dos registros criados por esta suíte. Serve para achá-los depois.
MARCA = "LT-PROMO"


def chamar(ctx, sessao, grupo, metodo, rota, rota_rotulo, corpo=None, esperado="2xx"):
    """Uma requisição medida. Mesmo contrato do helper da suíte `comanda`."""
    inicio = time.time()
    if metodo == "GET":
        resposta = sessao.get(rota)
    elif metodo == "DELETE":
        resposta = sessao.delete(rota, corpo or {})
    elif metodo == "PATCH":
        resposta = sessao.patch(rota, corpo or {})
    else:
        resposta = sessao.post(rota, corpo or {}, idempotency_key=str(uuid.uuid4()))
    ctx.record(SUITE, f"{SUITE}::{grupo}", metodo, rota_rotulo, resposta,
               expectation=esperado, started=inicio)
    return resposta


def motivo(resposta):
    """A frase que o backend devolveu, para a verificação dizer O QUE recusou."""
    corpo = resposta.json() if hasattr(resposta, "json") else None
    if isinstance(corpo, dict):
        erro = corpo.get("error")
        if isinstance(erro, dict):
            texto = erro.get("message")
            if isinstance(texto, dict):
                return " ".join(str(v) for v in texto.values())
            if texto:
                return str(texto)
        detalhe = corpo.get("detail")
        if detalhe:
            return detalhe if isinstance(detalhe, str) else str(detalhe)
    return (resposta.error or "")[:160]


def dinheiro(valor):
    """Decimal, ou `None` quando não é número. Campo ausente não é zero."""
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return None


def saturado(resposta):
    """503/429 é o alvo dizendo "cheguei ao teto", não defeito de lógica."""
    return resposta.status in (429, 503) or bool(resposta.error)


# ──────────────────────────────────── fase 0: cadastro da promoção

def fase_preparo(ctx, refs):
    """Cria a tabela de desconto, duas regras e os cupons da suíte.

    Cadastro PRÓPRIO, com marca: depender de o cenário já ter promoção faria a
    suíte passar por não ter o que medir, que é o pior resultado possível — um
    verde que não provou nada.
    """
    ctx.log(f"[{SUITE}] fase 0/6 — cadastro da promoção e dos cupons")
    produtos = refs.unit_products or []
    if not produtos:
        ctx.check(SUITE, "existe produto para promover", False,
                  "nenhum produto unitário no cenário")
        return None

    alvo = produtos[0]
    base = dinheiro(alvo.get("sale_price")) or Decimal("10.00")
    # O "por" é metade do cadastrado, e o "de" é MAIOR que ele: é o encarte real
    # ("de 30 por 15" num produto de 20), e é o caso que só o vínculo carrega.
    por = (base / 2).quantize(Decimal("0.01"))
    de = (base * Decimal("1.5")).quantize(Decimal("0.01"))

    sufixo = uuid.uuid4().hex[:6]
    tabela = chamar(ctx, ctx.session, "criar_tabela", "POST",
                    "/api/v1/promotions/discount-tables/",
                    "/api/v1/promotions/discount-tables/",
                    {"name": f"{MARCA} tabela {sufixo}", "is_enabled": True})
    if tabela.status not in (200, 201):
        ctx.check(SUITE, "a tabela de desconto foi criada", False,
                  f"HTTP {tabela.status}: {motivo(tabela)}")
        return None
    tabela_id = (tabela.json() or {}).get("id")

    regra = chamar(ctx, ctx.session, "criar_regra", "POST",
                   "/api/v1/promotions/rules/",
                   "/api/v1/promotions/rules/",
                   {"table": tabela_id, "name": f"{MARCA} encarte {sufixo}",
                    "position": 1, "target_type": "products",
                    "discount_kind": "fixed", "discount_value": "0",
                    "product_links": [{"product": alvo.get("id"),
                                       "promotional_price": str(por),
                                       "compare_at_price": str(de)}]})
    if regra.status not in (200, 201):
        ctx.check(SUITE, "a regra de desconto foi criada", False,
                  f"HTTP {regra.status}: {motivo(regra)}")
        return None

    cenario = {
        "tabela": tabela_id,
        "produto": str(alvo.get("id")),
        "base": base,
        "por": por,
        "de": de,
        "sufixo": sufixo,
    }
    ctx.note(SUITE, f"promoção pronta: produto a {base}, encarte de {de} por {por}")
    return cenario


# ──────────────────────────────────── fase 1: o preço sob leitura concorrente

def fase_preco_concorrente(ctx, refs, cenario):
    """Muitos terminais lendo o catálogo enquanto a tabela liga e desliga.

    A pergunta é estreita de propósito: o preço lido é SEMPRE um dos dois que
    existem — o de prateleira ou o da promoção? Um terceiro valor significaria
    resolução parcial (a regra encontrada, o vínculo não), e no caixa isso é
    cobrar um preço que ninguém cadastrou.
    """
    ctx.log(f"[{SUITE}] fase 1/6 — leitura do preço com a tabela oscilando")
    produto = cenario["produto"]
    esperados = {cenario["base"], cenario["por"]}
    estranhos = []
    incoerentes = []
    lidos = 0
    trava = threading.Lock()
    parar = threading.Event()

    def oscilar():
        """Liga e desliga a tabela durante a leitura. É o que cria a corrida."""
        while not parar.wait(0.35):
            chamar(ctx, ctx.session, "alternar_tabela", "POST",
                   f"/api/v1/promotions/discount-tables/{cenario['tabela']}/toggle/",
                   "/api/v1/promotions/discount-tables/{id}/toggle/", {})

    def ler(worker, _iteracao):
        sessao = clone(ctx.session, terminal_name=f"LT-PROMO-{worker + 1}")
        resposta = chamar(ctx, sessao, "ler_produto", "GET",
                          f"/api/v1/menu/products/{produto}/",
                          "/api/v1/menu/products/{id}/")
        if resposta.status != 200 or saturado(resposta):
            return
        corpo = resposta.json() or {}
        atual = dinheiro(corpo.get("current_price"))
        riscado = dinheiro(corpo.get("compare_at_price"))
        cheio = dinheiro(corpo.get("sale_price"))
        with trava:
            nonlocal lidos
            lidos += 1
            if atual is None or atual not in esperados:
                estranhos.append(str(atual))
            # O riscado só existe quando há desconto, e nunca abaixo do cobrado:
            # um "de" menor que o "por" é propaganda enganosa impressa no cupom.
            if riscado is not None and atual is not None and riscado <= atual:
                incoerentes.append(f"de {riscado} <= por {atual}")
            # O cadastrado NUNCA muda, com ou sem promoção. Se ele oscilar, a
            # promoção está escrevendo no produto — o defeito que o desenho
            # inteiro existe para impedir.
            if cheio is not None and cheio != cenario["base"]:
                incoerentes.append(f"cadastrado virou {cheio}")

    oscilador = threading.Thread(target=oscilar, daemon=True)
    oscilador.start()
    try:
        LoadRunner(workers=ctx.config.workers, rate=ctx.config.rate,
                   duration=max(4.0, ctx.config.duration / 3)).run(ler)
    finally:
        parar.set()
        oscilador.join(timeout=2)

    # A tabela volta LIGADA: as fases seguintes dependem do estado conhecido, e
    # um toggle ímpar deixaria a promoção desligada sem ninguém ter pedido.
    _garantir_tabela_ligada(ctx, cenario)

    ctx.check(SUITE, "o preço lido é sempre um preço que existe",
              not estranhos,
              f"{len(estranhos)} leitura(s) com valor fora de {sorted(esperados)}: "
              f"{sorted(set(estranhos))[:5]}" if estranhos else f"{lidos} leituras")
    ctx.check(SUITE, "o riscado e o cadastrado se mantêm coerentes",
              not incoerentes,
              "; ".join(sorted(set(incoerentes))[:4]))
    return lidos


def _garantir_tabela_ligada(ctx, cenario):
    leitura = chamar(ctx, ctx.session, "conferir_tabela", "GET",
                     f"/api/v1/promotions/discount-tables/{cenario['tabela']}/",
                     "/api/v1/promotions/discount-tables/{id}/")
    if leitura.status == 200 and (leitura.json() or {}).get("is_enabled") is False:
        chamar(ctx, ctx.session, "alternar_tabela", "POST",
               f"/api/v1/promotions/discount-tables/{cenario['tabela']}/toggle/",
               "/api/v1/promotions/discount-tables/{id}/toggle/", {})


# ──────────────────────────────────── fase 2: a disputa entre tabelas

def fase_disputa(ctx, refs, cenario):
    """Duas tabelas alcançam o mesmo produto: a MAIS ANTIGA tem de ganhar.

    Sob leitura concorrente, e não uma vez: se a ordenação da disputa depender da
    ordem que o banco devolveu, ela acerta quase sempre e erra de vez em quando —
    que é o modo mais caro de errar, porque ninguém consegue reproduzir.
    """
    ctx.log(f"[{SUITE}] fase 2/6 — disputa entre duas tabelas pelo mesmo produto")
    nova = chamar(ctx, ctx.session, "criar_tabela", "POST",
                  "/api/v1/promotions/discount-tables/",
                  "/api/v1/promotions/discount-tables/",
                  {"name": f"{MARCA} tabela nova {cenario['sufixo']}", "is_enabled": True})
    if nova.status not in (200, 201):
        ctx.note(SUITE, f"disputa não medida: segunda tabela HTTP {nova.status}")
        return
    nova_id = (nova.json() or {}).get("id")
    # A tabela nova desconta MAIS. Se ela vencer, a prioridade está pela
    # vantagem, e não pela promessa mais antiga.
    mais_barato = (cenario["por"] / 2).quantize(Decimal("0.01"))
    regra = chamar(ctx, ctx.session, "criar_regra", "POST",
                   "/api/v1/promotions/rules/",
                   "/api/v1/promotions/rules/",
                   {"table": nova_id, "name": f"{MARCA} mais barato", "position": 1,
                    "target_type": "products", "discount_kind": "fixed",
                    "discount_value": "0",
                    "product_links": [{"product": cenario["produto"],
                                       "promotional_price": str(mais_barato)}]})
    if regra.status not in (200, 201):
        ctx.note(SUITE, f"disputa não medida: regra nova HTTP {regra.status}")
        return

    venceu_o_novo = []
    trava = threading.Lock()

    def ler(worker, _iteracao):
        sessao = clone(ctx.session, terminal_name=f"LT-DISPUTA-{worker + 1}")
        resposta = chamar(ctx, sessao, "ler_produto", "GET",
                          f"/api/v1/menu/products/{cenario['produto']}/",
                          "/api/v1/menu/products/{id}/")
        if resposta.status != 200 or saturado(resposta):
            return
        atual = dinheiro((resposta.json() or {}).get("current_price"))
        if atual is not None and atual == mais_barato:
            with trava:
                venceu_o_novo.append(str(atual))

    LoadRunner(workers=ctx.config.workers, rate=ctx.config.rate,
               duration=max(3.0, ctx.config.duration / 4)).run(ler)

    ctx.check(SUITE, "a tabela mais antiga ganha a disputa, sempre",
              not venceu_o_novo,
              f"{len(venceu_o_novo)} leitura(s) cobraram {mais_barato} "
              f"(a tabela nova venceu) em vez de {cenario['por']}")
    # Desliga a tabela nova: as fases de cupom conferem valor, e um segundo
    # desconto ativo mudaria o total sem a fase ter pedido.
    chamar(ctx, ctx.session, "alternar_tabela", "POST",
           f"/api/v1/promotions/discount-tables/{nova_id}/toggle/",
           "/api/v1/promotions/discount-tables/{id}/toggle/", {})


# ──────────────────────────────────── orquestração

def run(ctx):
    inicio = time.time()
    refs = ctx.refs
    if not (refs.restaurant or {}).get("id"):
        ctx.check(SUITE, "há restaurante no cenário", False,
                  "nenhum restaurante na conta — rode `manage.py seed_demo` antes")
        return

    cenario = fase_preparo(ctx, refs)
    if cenario is None:
        return

    fase_preco_concorrente(ctx, refs, cenario)
    fase_disputa(ctx, refs, cenario)
    promocoes_cupom.fase_compra_unica(ctx, refs, cenario)
    promocoes_cupom.fase_limite_total(ctx, refs, cenario)
    promocoes_cupom.fase_cupom_no_pagamento(ctx, refs, cenario)
    promocoes_operador.fase_codigo_do_operador(ctx, refs, cenario)

    ctx.note(SUITE, f"suite concluída em {time.time() - inicio:.1f}s")
