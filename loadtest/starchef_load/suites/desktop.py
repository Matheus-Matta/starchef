"""Suite DESKTOP — frota de PDVs simulados, online e offline ao mesmo tempo.

Um Caixa Principal e N Caixas Secundarios, cada um com terminal proprio
(`X-Terminal-Id`), fila propria e queda de rede propria. O secundario nunca
fala com a nuvem: ele entrega ao principal, que entrega ao backend — a mesma
cadeia do sistema real.

No fim vem a parte que importa mais que a vazao: **conferir que a carga nao
cobrou ninguem duas vezes**.
"""
import time

from ..auth import clone
from ..sim import shift
from ..sim.outbox import DONE
from ..sim.terminal import PRINCIPAL, SECONDARY, Terminal
from ..workers import run_parallel

SUITE = "desktop"


def montar_frota(ctx):
    principal = Terminal(
        ctx, SUITE, clone(ctx.session, terminal_name="LT-PDV-principal"),
        "LT-PDV-principal", role=PRINCIPAL,
    )
    secundarios = [
        Terminal(
            ctx, SUITE, clone(ctx.session, terminal_name=f"LT-PDV-secundario-{indice + 1}"),
            f"LT-PDV-secundario-{indice + 1}", role=SECONDARY, upstream=principal,
        )
        for indice in range(max(0, ctx.config.terminals - 1))
    ]
    return principal, secundarios


def fase_turnos(ctx, principal, secundarios):
    ctx.log(
        f"[{SUITE}] fase 1/4 — {1 + len(secundarios)} terminais x {ctx.config.sales} vendas, "
        f"{int(ctx.config.offline_ratio * 100)}% de chance de cair a rede por venda"
    )
    frota = [principal, *secundarios]

    def rodar(item):
        indice, terminal = item
        rng = ctx.rng(indice * 7717 + 3)
        shift.turno(terminal, ctx.refs, rng, ctx.config, com_caixa=(terminal.role == PRINCIPAL))

    run_parallel(list(enumerate(frota)), rodar, workers=min(len(frota), ctx.config.workers))
    for terminal in frota:
        ctx.note(SUITE, f"terminal {terminal.name}: {terminal.summary()}")


def fase_principal_fora(ctx, principal, secundarios):
    """O principal cai; os secundarios continuam vendendo na fila deles."""
    if not secundarios:
        return
    ctx.log(f"[{SUITE}] fase 2/4 — Caixa Principal fora do ar; {len(secundarios)} secundarios vendendo na fila")
    principal.go_offline("(queda proposital do principal)")

    def rodar(item):
        indice, terminal = item
        rng = ctx.rng(indice * 104729 + 11)
        for _ in range(max(2, ctx.config.sales // 3)):
            shift.executar_venda(terminal, ctx.refs, rng, ctx.config.chaos_ratio)

    run_parallel(list(enumerate(secundarios)), rodar, workers=min(len(secundarios), ctx.config.workers))
    presos = sum(len(t.outbox.pending) for t in secundarios)
    ctx.check(
        SUITE, "secundario continua vendendo com o principal fora",
        presos > 0, f"{presos} operacoes esperando na fila dos secundarios",
    )
    principal.go_online()
    escoado = [terminal.reconnect() for terminal in secundarios]
    pendentes = sum(resultado["pendentes"] for resultado in escoado)
    entregues = sum(resultado["entregues"] for resultado in escoado)
    ctx.check(
        SUITE, "fila dos secundarios escoa quando o principal volta",
        entregues > 0, f"{entregues} entregues, {pendentes} ainda pendentes",
    )


def fase_tempestade_offline(ctx, principal, secundarios):
    """Todo mundo offline, vende muito, e volta ao mesmo tempo — o pior caso."""
    ctx.log(f"[{SUITE}] fase 3/4 — apagao geral: todos offline, venda em massa e retorno simultaneo")
    frota = [principal, *secundarios]
    for terminal in frota:
        terminal.go_offline("(apagao geral)")

    def rodar(item):
        indice, terminal = item
        rng = ctx.rng(indice * 33331 + 17)
        for _ in range(max(3, ctx.config.sales // 2)):
            shift.executar_venda(terminal, ctx.refs, rng, ctx.config.chaos_ratio)

    run_parallel(list(enumerate(frota)), rodar, workers=min(len(frota), ctx.config.workers))
    acumulado = sum(len(t.outbox.pending) for t in frota)
    ctx.note(SUITE, f"apagao acumulou {acumulado} operacoes nas filas")
    inicio = time.time()
    run_parallel(list(enumerate(frota)), lambda item: item[1].reconnect(), workers=len(frota))
    ctx.note(SUITE, f"retorno simultaneo escoou as filas em {time.time() - inicio:.1f}s")
    resumo = [t.outbox.status() for t in frota]
    restantes = sum(r["pendentes"] for r in resumo)
    detalhe = (
        f"{restantes} pendentes ({sum(r['em_espera'] for r in resumo)} em backoff, "
        f"{sum(r['orfas'] for r in resumo)} orfas de dependencia, "
        f"{sum(r['recusadas'] for r in resumo)} recusadas, "
        f"tipos pendentes: {_tipos_pendentes(frota)}); ultimo erro: "
        + (next((r["ultimo_erro"] for r in resumo if r["ultimo_erro"]), "nenhum"))
    )
    ctx.check(SUITE, "nenhuma operacao ficou presa apos o retorno", restantes == 0, detalhe)


def _tipos_pendentes(frota):
    """Que OPERACOES sobraram na fila — "333 pendentes" sozinho nao aciona ninguem."""
    contagem = {}
    for terminal in frota:
        for operacao in terminal.outbox.pending:
            contagem[operacao.kind] = contagem.get(operacao.kind, 0) + 1
    return ", ".join(f"{kind}={total}" for kind, total in sorted(contagem.items())) or "nenhuma"


def fase_reenvio_duplicado(ctx, principal, secundarios):
    """Reenvia recebimentos ja entregues: a chave de idempotencia tem de segurar."""
    ctx.log(f"[{SUITE}] fase 4/4 — reenvio das MESMAS operacoes de recebimento (idempotencia)")
    reenviadas = 0
    for terminal in [principal, *secundarios]:
        for venda in terminal.sales:
            operacao = venda.get("pagamento")
            if not venda.get("pagamento_ok") or operacao is None or reenviadas >= 40:
                continue
            terminal.replay_duplicate(operacao)
            reenviadas += 1
    ctx.note(SUITE, f"{reenviadas} recebimentos reenviados com a chave original")


def verificar_cobranca(ctx, principal, secundarios):
    """A pergunta que decide se o offline pode ir para producao: cobrou duas vezes?

    Contar pagamentos por pedido nao serve como criterio, e a razao e do
    dominio: a comanda e REUTILIZAVEL. `open-command` devolve o pedido aberto
    quando ela ja esta ocupada, entao varias vendas caem no mesmo pedido e pagam
    em parcelas — e o pedido pode ainda carregar recebimentos de antes desta
    execucao. Cinco recebimentos legitimos de R$ 10 num pedido de R$ 377 nao sao
    duplicidade.

    O criterio que realmente prova a propriedade e a CHAVE: cada operacao de
    recebimento entregue tem de corresponder a exatamente um pagamento no
    servidor, carregando o proprio `operation_id` como chave de idempotencia.
    Mais de um significa que a mesma operacao foi aplicada duas vezes; nenhum
    significa que o dinheiro nao chegou. Este criterio independe do que ja havia
    no pedido.
    """
    entregues = {}
    for terminal in [principal, *secundarios]:
        for venda in terminal.sales:
            operacao = venda.get("pagamento")
            if operacao is None or operacao.case != "valido" or operacao.status != DONE:
                continue
            referencia = venda["order_ref"]
            order_id = str(terminal.outbox.id_map.get(referencia, referencia))
            if order_id.startswith("offline-"):
                continue
            entregues.setdefault(order_id, set()).add(operacao.operation_id)

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
        SUITE, "nenhum recebimento foi aplicado duas vezes",
        duplicadas == 0 and conferidas > 0,
        f"{duplicadas} operacoes de recebimento viraram mais de um pagamento "
        f"em {conferidas} conferidas ({ausentes} nao encontradas no servidor)"
        + ("" if conferidas else " — nenhum recebimento valido chegou, nada a concluir"),
    )

    saude = ctx.api.request("GET", "/health/")
    ctx.check(SUITE, "backend saudavel apos a frota de PDVs", saude.status == 200, f"HTTP {saude.status}")


def run(ctx):
    inicio = time.time()
    principal, secundarios = montar_frota(ctx)
    fase_turnos(ctx, principal, secundarios)
    fase_principal_fora(ctx, principal, secundarios)
    fase_tempestade_offline(ctx, principal, secundarios)
    fase_reenvio_duplicado(ctx, principal, secundarios)
    verificar_cobranca(ctx, principal, secundarios)
    ctx.note(SUITE, f"suite concluida em {time.time() - inicio:.1f}s")
    return principal
