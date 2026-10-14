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
2. **Turno** — vendas concorrentes pela venda inteira (`/orders/submit/`):
   simula, conclui; com cupom válido e recusado e pagamento dividido
   (`desktop_venda.py`).
3. **Fiscal** — emissão, e a regra que hoje importa: recusa TEM de dizer o
   motivo.
4. **Conferência** — ninguém foi cobrado duas vezes.
"""
import random
import threading
import time
import uuid
from decimal import Decimal

from ..auth import clone
from ..workers import LoadRunner
from . import desktop_venda

SUITE = "desktop"

#: O que o app pede ao abrir, na ordem em que ele pede.
#: Extraído das chamadas reais de `pdv_desktop/lib`.
#:
#: Já foi testado juntar as sete numa rota agregadora `/pdv/bootstrap/`, e ela
#: FICOU PIOR sob carga: 13.786ms contra 8.145ms no pior caso (0,6x). O motivo é
#: que sob saturação o gargalo é TEMPO DE WORKER, não ida-e-volta. Juntar não
#: reduz o trabalho — concentra tudo num handler que segura um worker do
#: gunicorn, enquanto as sete pequenas se intercalam entre eles. E numa LAN,
#: onde o RTT é desprezível, agregar não tem o que economizar.
#:
#: O caminho promissor é outro: payload MENOR na abertura. O serializer de
#: produto carrega variações, ficha técnica, adicionais e imagens — nada disso
#: é usado para desenhar a grade inicial.
ROTAS_DE_ABERTURA = [
    "/api/v1/auth/me/",
    "/api/v1/menu/categories/?page_size=100&is_active=true",
    "/api/v1/menu/products/?page_size=300&is_active=true",
    "/api/v1/tables/?page_size=300",
    "/api/v1/commands/?page_size=300&is_active=true",
    "/api/v1/payments/methods/?page_size=100&is_active=true",
    "/api/v1/cash-stations/?page_size=300&is_active=true",
]


def fase_abertura(ctx):
    """N terminais ligando ao mesmo tempo. É o pior instante do dia.

    Sete leituras sequenciais, como o app faz. Já foi medida a alternativa de
    juntá-las numa rota agregadora: ela NÃO ajudou — ver o comentário em
    `ROTAS_DE_ABERTURA`.
    """
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

    O PDV real abre a sessão antes de vender; pular isso faria a suíte reportar
    "0 vendas" e parecer defeito do sistema quando é pré-condição do teste
    faltando.

    A estação tem operadores autorizados, e um usuário só pode estar vinculado
    a UMA por vez — então adivinhar qual usar não funciona. A suíte tenta as
    estações em ordem e fica com a primeira que abrir: é o que um operador
    faria, e não depende de conhecer o modelo de permissão.
    """
    ctx.log(f"[{SUITE}] fase 2/5 — abertura do caixa")
    atual = ctx.session.get("/api/v1/cash-register/current/")
    if atual.status == 200 and (atual.json() or {}).get("id"):
        ctx.note(SUITE, "já havia caixa aberto; reaproveitado")
        return True

    lista = ctx.session.get("/api/v1/cash-stations/?page_size=50&is_active=true")
    corpo = lista.json() or {}
    estacoes = corpo.get("results") or corpo.get("data") or []
    if not estacoes:
        ctx.note(SUITE, "nenhuma estação de caixa no cenário; venda não exercitada")
        return False

    recusas = []
    for estacao in estacoes:
        inicio = time.time()
        resposta = ctx.session.post(
            "/api/v1/cash-register/open/",
            {"cash_station": estacao.get("id"), "opening_amount": "200.00",
             "notes": "carga"},
            idempotency_key=str(uuid.uuid4()),
        )
        ctx.record(SUITE, f"{SUITE}::abrir_caixa", "POST",
                   "/api/v1/cash-register/open/", resposta,
                   expectation="2xx", started=inicio)
        # 409 é "já existe sessão aberta nesta estação" — sucesso para o que a
        # suíte precisa, não falha.
        if resposta.status in (200, 201, 409):
            ctx.note(
                SUITE,
                f"caixa aberto na estação '{estacao.get('name', '?')}' "
                f"(HTTP {resposta.status})",
            )
            return True
        recusas.append(f"{estacao.get('name', '?')}: HTTP {resposta.status}")

    ctx.check(
        SUITE, "há caixa aberto para receber",
        False,
        "nenhuma estação aceitou abrir — " + "; ".join(recusas[:4]),
    )
    return False


def fase_turno(ctx, refs):
    """Vendas concorrentes pelo `/orders/submit/` (`desktop_venda.py`).

    Cada trabalhador é um PDV; os cenários (simples, cupom válido e recusado,
    pagamento dividido) se misturam como num turno de verdade.
    """
    ctx.log(f"[{SUITE}] fase 3/5 — turno de vendas concorrentes (venda inteira)")
    rng = ctx.rng(31337)
    cupom = desktop_venda.criar_cupom(ctx)
    resultados = []
    trava = threading.Lock()

    def vender(indice, _iteracao):
        sessao = clone(ctx.session, terminal_name=f"LT-PDV-{indice + 1}")
        with trava:
            sorteio = random.Random(rng.random())
        venda = desktop_venda.uma_venda(ctx, sessao, refs, sorteio, cupom)
        if venda:
            with trava:
                resultados.append(venda)

    LoadRunner(
        workers=ctx.config.workers, rate=ctx.config.rate,
        duration=ctx.config.duration, count=ctx.config.count,
    ).run(vender)

    vendas = [r for r in resultados if r.get("pedido")]
    ctx.note(SUITE, f"turno: {len(vendas)} vendas concluídas de ponta a ponta")
    desktop_venda.conferir_cenarios(ctx, resultados)
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

    # O que É defeito e o que NÃO é, porque a primeira versão desta fase
    # confundiu os dois:
    #
    # Vários pagamentos num pedido é CONTA DIVIDIDA — funcionalidade. Reprovar
    # por isso acusava o sistema de cobrança dupla num comportamento correto.
    #
    # Cobrança dupla de verdade tem duas assinaturas: a mesma chave de
    # idempotência gerando dois recebimentos, ou a soma dos pagamentos passando
    # do total do pedido. São essas que valem verificar.
    chaves = {}
    repetidas = 0
    acima_do_total = 0
    # DEDUPLICAR os pedidos antes de ler, e isto não é detalhe: vários caixas
    # abrem a MESMA comanda, então o mesmo pedido aparece repetido em `vendas`.
    # Lendo-o duas vezes, cada chave de idempotência era contada em dobro e a
    # fase acusava o sistema de cobrança dupla — com a idempotência funcionando
    # perfeitamente. Acusar o sistema pelo erro do teste é pior que não testar.
    unicos = list(dict.fromkeys(v["pedido"] for v in vendas))
    for pedido_id in unicos[: max(1, min(40, len(unicos)))]:
        resposta = ctx.session.get(f"/api/v1/orders/{pedido_id}/")
        if resposta.status != 200:
            continue
        pedido = resposta.json() or {}
        pagamentos = pedido.get("payments") or []

        for pagamento in pagamentos:
            chave = pagamento.get("idempotency_key")
            if not chave:
                continue
            chaves[chave] = chaves.get(chave, 0) + 1
            if chaves[chave] == 2:
                repetidas += 1

        pago = sum(Decimal(str(p.get("amount") or "0")) for p in pagamentos)
        total = Decimal(str(pedido.get("total") or pedido.get("total_amount") or "0"))
        if total and pago > total:
            acima_do_total += 1

    ctx.check(
        SUITE, "nenhuma chave de idempotência gerou dois recebimentos",
        repetidas == 0,
        f"{repetidas} chave(s) com mais de um pagamento — a idempotência não segurou",
    )
    ctx.check(
        SUITE, "ninguém pagou mais que o total do pedido",
        acima_do_total == 0,
        f"{acima_do_total} pedido(s) com soma de pagamentos ACIMA do total",
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
