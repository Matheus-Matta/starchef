"""Suite DESKTOP — o PDV desktop 3.x, que é só-conectado.

Esta suíte substituiu a da linhagem 1.8.x, que simulava um Caixa Principal com
Secundários entregando a ele. Aquela cadeia não existe mais: o `pdv_desktop`
fala direto com UM backend e não opera offline.

**A topologia é escolha de execução, não do código.** Aponte `--base-url` para
o backend da loja e você mede a operação com backend local; aponte para a nuvem
e mede o acesso direto. O que a suíte reproduz é o comportamento do app —
as mesmas rotas, na mesma ordem, com a mesma concorrência.

As fases seguem o dia do caixa:

1. **Abertura** — o app dispara sete leituras de uma vez ao abrir. Com N
   terminais ligando às 8h, isso é uma rajada simultânea, não uma fila.
2. **Turno** — vendas concorrentes: abre, lança item, paga, conclui.
3. **Fiscal** — emissão, e a regra que hoje importa: recusa TEM de dizer o
   motivo.
4. **Conferência** — ninguém foi cobrado duas vezes.
"""
import threading
import time
import uuid
from decimal import Decimal

from ..auth import clone
from ..workers import LoadRunner

SUITE = "desktop"

#: O que o app pede ao abrir, na ordem em que ele pede.
#: Extraído das chamadas reais de `pdv_desktop/lib`.
ROTAS_DE_ABERTURA = [
    "/api/v1/auth/me/",
    "/api/v1/menu/categories/?page_size=100&is_active=true",
    "/api/v1/menu/products/?page_size=300&is_active=true",
    "/api/v1/tables/?page_size=300",
    "/api/v1/commands/?page_size=300&is_active=true",
    "/api/v1/payments/methods/?page_size=100&is_active=true",
    "/api/v1/cash-stations/?page_size=300&is_active=true",
]


def _preco(produto):
    try:
        return Decimal(str(produto.get("price") or produto.get("sale_price") or "0"))
    except (TypeError, ValueError):
        return Decimal("0")


def fase_abertura(ctx):
    """N terminais ligando ao mesmo tempo. É o pior instante do dia."""
    ctx.log(f"[{SUITE}] fase 1/5 — abertura simultânea dos terminais")
    # `--terminals` é o botão que descreve a FROTA; `--workers` descreve a
    # pressão de escrita. Misturar os dois faria o perfil "pesado" abrir 128
    # caixas, que nenhuma loja tem.
    terminais = max(2, min(24, ctx.config.terminals or 4))
    latencias = []
    trava = threading.Lock()

    def abrir(indice, _iteracao):
        sessao = clone(ctx.session, terminal_name=f"LT-PDV-{indice + 1}")
        inicio = time.perf_counter()
        for rota in ROTAS_DE_ABERTURA:
            comeco = time.time()
            resposta = sessao.get(rota)
            ctx.record(
                SUITE, f"{SUITE}::abertura", "GET", rota.split("?")[0],
                resposta, expectation="2xx", started=comeco,
            )
        with trava:
            latencias.append((time.perf_counter() - inicio) * 1000)

    LoadRunner(workers=terminais, count=terminais).run(abrir)

    if latencias:
        latencias.sort()
        pior = latencias[-1]
        ctx.note(
            SUITE,
            f"abertura de {terminais} terminais simultâneos: "
            f"mediana {latencias[len(latencias) // 2]:.0f}ms, pior {pior:.0f}ms "
            f"({len(ROTAS_DE_ABERTURA)} leituras cada)",
        )
        # O operador está de pé esperando a tela abrir. Cinco segundos já é
        # ruim; dez é o caixa chamando o suporte.
        ctx.check(
            SUITE, "o terminal abre em tempo tolerável mesmo com todos ligando juntos",
            pior < 10000,
            f"pior abertura levou {pior:.0f}ms com {terminais} terminais simultâneos",
        )


def fase_abrir_caixa(ctx, refs):
    """Sem caixa aberto o backend recusa o recebimento — e está certo.

    O PDV real abre a sessão antes de vender; pular isso aqui faria a suíte
    reportar "0 vendas" e parecer defeito do sistema quando é ausência de
    pré-condição do teste.
    """
    ctx.log(f"[{SUITE}] fase 2/5 — abertura do caixa")
    atual = ctx.session.get("/api/v1/cash-register/current/")
    if atual.status == 200 and (atual.json() or {}).get("id"):
        ctx.note(SUITE, "já havia caixa aberto; reaproveitado")
        return True

    estacao = (refs.cash_station or {}).get("id")
    if not estacao:
        ctx.note(SUITE, "nenhuma estação de caixa no cenário; venda não será exercitada")
        return False

    # A estação tem lista de operadores autorizados, e o usuário do teste pode
    # não estar nela — "O operador não está vinculado a este caixa". Isso é
    # pré-condição de CENÁRIO, não defeito do sistema: a suíte se vincula e
    # segue, em vez de reportar falha e esconder o que ela veio medir.
    eu = ctx.session.get("/api/v1/auth/me/")
    meu_id = (eu.json() or {}).get("id") if eu.status == 200 else None
    if meu_id:
        vinculo = ctx.session.patch(
            f"/api/v1/cash-stations/{estacao}/", {"operators": [meu_id]}
        )
        if vinculo.status not in (200, 202):
            ctx.note(
                SUITE,
                f"não foi possível vincular o operador à estação "
                f"(HTTP {vinculo.status}); a abertura pode ser recusada",
            )

    inicio = time.time()
    resposta = ctx.session.post(
        "/api/v1/cash-register/open/",
        {"cash_station": estacao, "opening_amount": "200.00", "notes": "carga"},
        idempotency_key=str(uuid.uuid4()),
    )
    ctx.record(SUITE, f"{SUITE}::abrir_caixa", "POST", "/api/v1/cash-register/open/",
               resposta, expectation="2xx", started=inicio)
    aberto = resposta.status in (200, 201)
    ctx.check(
        SUITE, "o caixa abre",
        aberto,
        f"HTTP {resposta.status} ao abrir — sem caixa não há recebimento",
    )
    return aberto


def _uma_venda(ctx, sessao, refs, rng):
    """Abre, lança um item, paga e conclui. Devolve o total cobrado."""
    restaurante = str((refs.restaurant or {}).get("id", ""))

    corpo = {"order_type": "counter", "restaurant": restaurante}
    if refs.command_codes and rng.random() < 0.6:
        rota, corpo = "/api/v1/orders/open-command/", {
            "command": rng.choice(refs.ids["commands"])
        }
    else:
        rota = "/api/v1/orders/"

    inicio = time.time()
    resposta = sessao.post(rota, corpo, idempotency_key=str(uuid.uuid4()))
    ctx.record(SUITE, f"{SUITE}::abrir_pedido", "POST", rota, resposta,
               expectation="2xx", started=inicio)
    if resposta.status not in (200, 201):
        return None
    pedido = (resposta.json() or {}).get("id")
    if not pedido:
        return None

    produto = rng.choice(refs.unit_products) if refs.unit_products else None
    if produto is None:
        return None
    inicio = time.time()
    item = sessao.post(
        f"/api/v1/orders/{pedido}/items/",
        {
            "product": produto.get("id"),
            "quantity": 1,
            "variations": [],
            "addons": [],
            # Conferencia, nao preco: o total autoritativo e do servidor.
            "expected_unit_price": str(_preco(produto)),
            "customer_note": "",
        },
        idempotency_key=str(uuid.uuid4()),
    )
    ctx.record(SUITE, f"{SUITE}::lancar_item", "POST", "/api/v1/orders/{id}/items/",
               item, expectation="2xx", started=inicio)
    if item.status not in (200, 201):
        return None

    metodo = (refs.payment_by_type.get("cash") or {}).get("id")
    if not metodo:
        return None
    valor = _preco(produto)
    inicio = time.time()
    # `/orders/{id}/pay/` — e nao `/payments/`, que responde 405. E a rota que
    # o app usa de verdade (`home_page_payment.dart`).
    pagamento = sessao.post(
        f"/api/v1/orders/{pedido}/pay/",
        {"payment_method": metodo, "amount": str(valor)},
        idempotency_key=str(uuid.uuid4()),
    )
    ctx.record(SUITE, f"{SUITE}::pagar", "POST", "/api/v1/orders/{id}/pay/", pagamento,
               expectation="2xx", started=inicio)
    if pagamento.status not in (200, 201):
        return None
    return {"pedido": pedido, "valor": valor}


def fase_turno(ctx, refs):
    """Vendas concorrentes. Aqui aparece qualquer serialização de escrita."""
    ctx.log(f"[{SUITE}] fase 3/5 — turno de vendas concorrentes")
    rng = ctx.rng(31337)
    vendas = []
    trava = threading.Lock()

    def vender(indice, _iteracao):
        sessao = clone(ctx.session, terminal_name=f"LT-PDV-{indice + 1}")
        venda = _uma_venda(ctx, sessao, refs, rng)
        if venda:
            with trava:
                vendas.append(venda)

    LoadRunner(
        workers=ctx.config.workers, rate=ctx.config.rate,
        duration=ctx.config.duration, count=ctx.config.count,
    ).run(vender)

    ctx.note(SUITE, f"turno: {len(vendas)} vendas concluídas de ponta a ponta")
    ctx.check(
        SUITE, "o turno produz vendas",
        bool(vendas),
        "nenhuma venda fechou — confira caixa aberto, produto ativo e forma de pagamento",
    )
    return vendas


def fase_fiscal(ctx, vendas):
    """Emissão — e a regra de hoje: recusa SEM motivo é defeito."""
    ctx.log(f"[{SUITE}] fase 4/5 — emissão fiscal")
    if not vendas:
        ctx.note(SUITE, "sem vendas; emissão não exercitada")
        return

    amostra = vendas[: max(1, min(10, len(vendas)))]
    sem_motivo = 0
    for venda in amostra:
        inicio = time.time()
        resposta = ctx.session.post(
            "/api/v1/invoices/emit/", {"order": venda["pedido"]},
            idempotency_key=str(uuid.uuid4()),
        )
        ctx.record(SUITE, f"{SUITE}::emitir", "POST", "/api/v1/invoices/emit/",
                   resposta, expectation="2xx", started=inicio)
        corpo = resposta.json() or {}
        if corpo.get("emitted") is False and not str(corpo.get("message") or "").strip():
            sem_motivo += 1

    ctx.note(SUITE, f"emissão exercitada em {len(amostra)} venda(s)")
    # Sem `message`, o PDV cai num texto fixo que ele inventa — e o operador lê
    # "o provedor fiscal não está configurado" para QUALQUER falha, inclusive
    # rejeição da SEFAZ. Foi assim que uma divergência de regime tributário
    # passou dias parecendo problema de provedor.
    ctx.check(
        SUITE, "toda recusa fiscal explica o motivo",
        sem_motivo == 0,
        f"{sem_motivo} recusa(s) vieram sem `message` — o PDV vai inventar a causa",
    )


def fase_conferencia(ctx, vendas):
    """A parte que importa mais que vazão: ninguém pagou duas vezes."""
    ctx.log(f"[{SUITE}] fase 5/5 — conferência do dinheiro")
    if not vendas:
        return

    duplicados = 0
    divergentes = 0
    for venda in vendas[: max(1, min(25, len(vendas)))]:
        resposta = ctx.session.get(f"/api/v1/orders/{venda['pedido']}/")
        if resposta.status != 200:
            continue
        pedido = resposta.json() or {}
        pagamentos = pedido.get("payments") or []
        if len(pagamentos) > 1:
            duplicados += 1
        total = sum(Decimal(str(p.get("amount") or "0")) for p in pagamentos)
        if total and total != venda["valor"]:
            divergentes += 1

    ctx.check(
        SUITE, "nenhuma venda foi cobrada duas vezes",
        duplicados == 0,
        f"{duplicados} pedido(s) com mais de um pagamento para uma cobrança só",
    )
    ctx.check(
        SUITE, "o valor cobrado bate com o lançado",
        divergentes == 0,
        f"{divergentes} pedido(s) com soma de pagamentos diferente do item lançado",
    )


def run(ctx):
    inicio = time.time()
    refs = ctx.refs
    fase_abertura(ctx)
    fase_abrir_caixa(ctx, refs)
    vendas = fase_turno(ctx, refs)
    fase_fiscal(ctx, vendas)
    fase_conferencia(ctx, vendas)
    ctx.note(SUITE, f"suite concluída em {time.time() - inicio:.1f}s")
