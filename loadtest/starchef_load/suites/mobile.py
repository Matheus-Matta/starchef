"""Suite MOBILE — enxame de aplicativos de garcom contra um Caixa Principal.

Mesma logica do desktop, um degrau abaixo na cadeia: o aparelho nao alcanca a
nuvem, so o principal. Alem da carga, verifica as tres regras que o app real
promete — cache marcado, leitura negada sem cache e dinheiro indisponivel sem
sessao de caixa confirmada.
"""
import time

from ..auth import clone, login
from ..sim import cash, shift
from ..sim.outbox import DONE
from ..sim.terminal import PRINCIPAL, Terminal
from ..sim.waiter import WaiterTerminal
from ..workers import run_parallel

SUITE = "mobile"

ROTAS_DO_APP = [
    "/api/v1/orders/?page_size=25",
    "/api/v1/menu/products/?page_size=50",
    "/api/v1/tables/?page_size=100",
    "/api/v1/commands/?page_size=100",
    "/api/v1/payments/methods/?page_size=50",
]


def _sessao_garcom(ctx, indice):
    """Tenta a credencial de garcom; sem ela, segue com a do orquestrador."""
    if indice == 0:
        try:
            return login(
                ctx.api, ctx.config.username, ctx.config.password,
                terminal_name=f"LT-garcom-{indice + 1}", client_kind="waiter_app",
            )
        except Exception:  # noqa: BLE001 — perfil nao-garcom e cenario esperado
            ctx.note(SUITE, "usuario do teste nao tem perfil de garcom; usando a credencial padrao")
    return clone(ctx.session, terminal_name=f"LT-garcom-{indice + 1}")


def montar_enxame(ctx):
    principal = Terminal(
        ctx, SUITE, clone(ctx.session, terminal_name="LT-PDV-principal-mobile"),
        "LT-PDV-principal-mobile", role=PRINCIPAL,
    )
    abertura = cash.abrir_caixa(principal, ctx.refs, ctx.rng(5))
    if abertura is not None:
        corpo = principal.execute(abertura)
        if isinstance(corpo, dict) and corpo.get("id"):
            principal.cash_register = str(corpo["id"])
    garcons = [
        WaiterTerminal(ctx, SUITE, _sessao_garcom(ctx, indice), f"LT-garcom-{indice + 1}", principal)
        for indice in range(max(1, ctx.config.waiters))
    ]
    return principal, garcons


def fase_salao_cheio(ctx, garcons):
    ctx.log(f"[{SUITE}] fase 1/3 — {len(garcons)} garcons lancando pedidos ao mesmo tempo")

    def rodar(item):
        indice, garcom = item
        rng = ctx.rng(indice * 19937 + 23)
        for rota in ROTAS_DO_APP:
            garcom.read(rota)
        for _ in range(max(2, ctx.config.sales // 2)):
            shift.executar_venda(garcom, ctx.refs, rng, ctx.config.chaos_ratio)

    run_parallel(list(enumerate(garcons)), rodar, workers=min(len(garcons), ctx.config.workers))


def fase_principal_fora(ctx, principal, garcons):
    ctx.log(f"[{SUITE}] fase 2/3 — Caixa Principal fora: leitura por cache e venda na fila do aparelho")
    principal.go_offline("(o caixa do salao foi desligado)")

    def rodar(item):
        indice, garcom = item
        rng = ctx.rng(indice * 65599 + 29)
        for rota in ROTAS_DO_APP:
            garcom.read(rota)
        garcom.read("/api/v1/rota/que/o/app/nunca/leu/")
        garcom.cash_session_available()
        for _ in range(max(2, ctx.config.sales // 3)):
            shift.executar_venda(garcom, ctx.refs, rng, ctx.config.chaos_ratio)

    run_parallel(list(enumerate(garcons)), rodar, workers=min(len(garcons), ctx.config.workers))

    hits = sum(g.cache.hits for g in garcons)
    negadas = sum(g.leituras_negadas for g in garcons)
    bloqueios = sum(g.dinheiro_bloqueado for g in garcons)
    presas = sum(len(g.outbox.pending) for g in garcons)
    ctx.check(SUITE, "leitura sem principal veio do cache", hits > 0, f"{hits} respostas servidas do cache")
    ctx.check(SUITE, "leitura sem cache falha em vez de inventar", negadas > 0, f"{negadas} leituras negadas")
    ctx.check(SUITE, "sessao de caixa nao vem do cache", bloqueios > 0, f"{bloqueios} recusas de dinheiro")
    ctx.check(SUITE, "aparelho continua vendendo na propria fila", presas > 0, f"{presas} operacoes enfileiradas")


def fase_retorno(ctx, principal, garcons):
    ctx.log(f"[{SUITE}] fase 3/3 — principal volta e {len(garcons)} filas escoam ao mesmo tempo")
    principal.go_online()
    inicio = time.time()
    run_parallel(list(enumerate(garcons)), lambda item: item[1].reconnect(),
                 workers=min(len(garcons), ctx.config.workers))
    resumo = [g.outbox.status() for g in garcons]
    restantes = sum(r["pendentes"] for r in resumo)
    ctx.note(SUITE, f"escoamento simultaneo levou {time.time() - inicio:.1f}s; {restantes} operacoes restantes")
    ctx.check(
        SUITE, "filas dos aparelhos escoaram apos o retorno", restantes == 0,
        f"{restantes} pendentes ({sum(r['em_espera'] for r in resumo)} em backoff, "
        f"{sum(r['orfas'] for r in resumo)} orfas); ultimo erro: "
        + (next((r["ultimo_erro"] for r in resumo if r["ultimo_erro"]), "nenhum")),
    )

    # Mesma correcao do desktop: varios garcons lancam na MESMA comanda, e o
    # pedido dela recebe pagamentos parciais legitimos. O que nao pode e o
    # servidor ter mais recebimentos do que os aparelhos entregaram.
    # Mesmo criterio do desktop: a chave prova a propriedade; a contagem por
    # pedido nao, porque a comanda e reutilizavel e o pedido acumula parcelas.
    entregues = {}
    for garcom in garcons:
        for venda in garcom.sales:
            operacao = venda.get("pagamento")
            if operacao is None or operacao.case != "valido" or operacao.status != DONE:
                continue
            referencia = str(garcom.outbox.id_map.get(venda["order_ref"], venda["order_ref"]))
            if referencia.startswith("offline-"):
                continue
            entregues.setdefault(referencia, set()).add(operacao.operation_id)

    duplicadas, ausentes, conferidas = 0, 0, 0
    for order_id, chaves in entregues.items():
        pagamentos = ctx.session.json_get(f"/api/v1/orders/{order_id}/payments/")
        if not isinstance(pagamentos, list):
            continue
        contagem = {}
        for pagamento in pagamentos:
            chave = str(pagamento.get("idempotency_key") or "")
            contagem[chave] = contagem.get(chave, 0) + 1
        for chave in chaves:
            conferidas += 1
            quantos = contagem.get(chave, 0)
            if quantos > 1:
                duplicadas += 1
            elif quantos == 0:
                ausentes += 1

    ctx.check(
        SUITE, "nenhum recebimento do salao foi aplicado duas vezes",
        duplicadas == 0 and conferidas > 0,
        f"{duplicadas} operacoes viraram mais de um pagamento em {conferidas} conferidas "
        f"({ausentes} nao encontradas no servidor)"
        + ("" if conferidas else " — nenhum recebimento valido chegou, nada a concluir"),
    )
    for garcom in garcons[:5]:
        ctx.note(SUITE, f"aparelho {garcom.name}: {garcom.summary()}")


def run(ctx):
    inicio = time.time()
    principal, garcons = montar_enxame(ctx)
    fase_salao_cheio(ctx, garcons)
    fase_principal_fora(ctx, principal, garcons)
    fase_retorno(ctx, principal, garcons)
    ctx.note(SUITE, f"suite concluida em {time.time() - inicio:.1f}s")
