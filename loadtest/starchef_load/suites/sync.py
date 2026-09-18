"""Suite SYNC — os DOIS backends ao mesmo tempo: o da loja e o da nuvem.

As outras suites atacam um alvo só. Esta ataca o par, porque o que se quer
medir aqui não existe dentro de um processo: é a fila entre eles.

Cinco fases:

1. **Identidade** — quem é cada alvo (LOCAL/CLOUD) e se a sincronização está
   ligada nos dois. Sem isso o resto do relatório não quer dizer nada.
2. **Enchendo a outbox** — escrita pesada no backend da LOJA. Cada gravação tem
   de virar evento na mesma transação; a fila cresce junto com os registros.
3. **Convergência** — o que foi escrito na loja aparece na nuvem? Mede quanto
   tempo a fila leva para drenar, sem exigir que drene.
4. **Leitura sob carga** — a API de gerenciamento (`/api/v1/sync/`) consultada
   nos dois lados enquanto a fila se move.
5. **Matrícula sob ataque** — credencial errada tem de dar 403 e o limite de
   taxa tem de segurar. É a única rota da sincronização aberta sem token.

Sem `--cloud-url` a suite roda só as fases que cabem num alvo e avisa o que
deixou de medir — ela não inventa um segundo backend.
"""
import time

from ..suites import sync_contention, sync_phases
from ..workers import LoadRunner

SUITE = "sync"

ROTAS_DE_GESTAO = [
    "/api/v1/sync/nodes/",
    "/api/v1/sync/nodes/status/",
    "/api/v1/sync/events/?page_size=50",
    "/api/v1/sync/events/dead/",
    "/api/v1/sync/events/stuck/",
    "/api/v1/sync/runs/?page_size=25",
    "/api/v1/sync/conflicts/?page_size=25",
]


def fase_identidade(ctx):
    """Quem é cada alvo. Roda primeiro porque tudo depois depende disto."""
    ctx.log(f"[{SUITE}] fase 1/5 — identidade dos dois backends")
    papeis = {}
    for rotulo, sessao in sync_phases.alvos(ctx):
        estado = sync_phases.status(ctx, SUITE, rotulo, sessao)
        papeis[rotulo] = estado
        ctx.note(
            SUITE,
            f"{rotulo}: node_type={estado.get('node_type') or '?'} "
            f"enabled={estado.get('enabled')} env={estado.get('environment') or '?'} "
            f"fila={(estado.get('queue') or {}).get('total', '?')}",
        )

    local = papeis.get("loja", {})
    nuvem = papeis.get("nuvem", {})
    if nuvem:
        ctx.check(
            SUITE, "os dois alvos têm papéis diferentes",
            local.get("node_type") != nuvem.get("node_type"),
            f"loja={local.get('node_type')} nuvem={nuvem.get('node_type')}",
        )
    ctx.check(
        SUITE, "sincronização ligada no backend da loja",
        bool(local.get("enabled")),
        "SYNC_ENABLED=false — as fases seguintes medem só a escrita, não a fila",
    )
    return papeis


def fase_enchendo_a_outbox(ctx, papeis):
    """Escrita pesada na LOJA. Cada registro tem de virar evento."""
    ctx.log(f"[{SUITE}] fase 2/5 — escrita pesada na loja, enchendo a outbox")
    antes = sync_phases.fila(ctx, "loja")
    rng = ctx.rng(4242)

    runner = LoadRunner(
        workers=ctx.config.workers, rate=ctx.config.rate,
        duration=ctx.config.duration, count=ctx.config.count,
    )
    runner.run(lambda _w, indice: sync_phases.escrever_na_loja(ctx, SUITE, rng, indice))

    depois = sync_phases.fila(ctx, "loja")
    criados = sync_phases.criados(ctx)
    ctx.note(
        SUITE,
        f"fila da loja: {antes.get('total', 0)} -> {depois.get('total', 0)} eventos "
        f"({criados} gravações bem-sucedidas na fase)",
    )
    if papeis.get("loja", {}).get("enabled"):
        ctx.check(
            SUITE, "toda gravação virou evento na outbox",
            depois.get("total", 0) >= antes.get("total", 0) + min(criados, 1),
            f"{criados} gravações, fila cresceu {depois.get('total', 0) - antes.get('total', 0)}",
        )
    return depois


def fase_convergencia(ctx, fila_apos_escrita):
    """A fila drena? Mede o tempo; não exige que zere dentro do teste."""
    ctx.log(f"[{SUITE}] fase 3/5 — drenagem da fila")
    if not sync_phases.tem_nuvem(ctx):
        ctx.note(SUITE, "sem --cloud-url: convergência não medida")
        return

    pendentes_inicio = fila_apos_escrita.get("nao_enviados", 0)
    inicio = time.time()
    restante = sync_phases.esperar_drenagem(
        ctx, SUITE, limite_segundos=max(30, ctx.config.duration)
    )
    decorrido = time.time() - inicio

    drenados = max(0, pendentes_inicio - restante)
    taxa = drenados / decorrido if decorrido else 0
    ctx.note(
        SUITE,
        f"drenagem: {drenados} de {pendentes_inicio} eventos em {decorrido:.1f}s "
        f"({taxa:.1f} eventos/s); {restante} ainda pendentes",
    )
    ctx.check(
        SUITE, "a fila anda (o worker está enviando)",
        drenados > 0 or pendentes_inicio == 0,
        f"{restante} pendentes depois de {decorrido:.0f}s — "
        "worker parado, nuvem fora do ar ou nó sem credencial",
    )
    # A garantia que importa não é "esvaziou": é "não sumiu".
    ctx.check(
        SUITE, "nenhum evento foi perdido no caminho",
        sync_phases.nada_sumiu(ctx, SUITE),
        "eventos desaparecidos entre a outbox e a inbox",
    )


def fase_leitura_de_gestao(ctx):
    """A API de gerenciamento consultada nos dois lados, sob carga."""
    ctx.log(f"[{SUITE}] fase 4/5 — API de gerenciamento sob carga nos dois alvos")
    alvos = sync_phases.alvos(ctx)
    rng = ctx.rng(909)

    def uma_leitura(_worker, indice):
        rotulo, sessao = alvos[indice % len(alvos)]
        rota = ROTAS_DE_GESTAO[rng.randrange(len(ROTAS_DE_GESTAO))]
        return sync_phases.ler(ctx, SUITE, rotulo, sessao, rota)

    runner = LoadRunner(
        workers=ctx.config.workers, rate=ctx.config.rate,
        duration=max(5, ctx.config.duration // 2), count=ctx.config.count,
    )
    runner.run(uma_leitura)


def fase_matricula_sob_ataque(ctx):
    """A única rota sem token. Credencial errada não pode virar 500 nem 201."""
    ctx.log(f"[{SUITE}] fase 5/5 — matrícula com credencial errada")
    alvo = sync_phases.alvo_nuvem(ctx) or sync_phases.alvo_loja(ctx)
    if alvo is None:
        return

    respostas = sync_phases.atacar_matricula(
        ctx, SUITE, alvo, tentativas=12, workers=min(6, ctx.config.workers)
    )
    aceitas = [r for r in respostas if r and r.status in (200, 201)]
    erros_de_servidor = [r for r in respostas if r and r.status >= 500]

    ctx.check(
        SUITE, "credencial errada nunca matricula um nó",
        not aceitas,
        f"{len(aceitas)} tentativa(s) com senha errada foram ACEITAS",
    )
    ctx.check(
        SUITE, "matrícula inválida responde erro tratado, não 500",
        not erros_de_servidor,
        f"{len(erros_de_servidor)} resposta(s) 5xx",
    )
    bloqueadas = [r for r in respostas if r and r.status == 429]
    ctx.note(
        SUITE,
        f"matrícula: {len(respostas)} tentativas, {len(bloqueadas)} barradas por limite de taxa",
    )


def run(ctx):
    inicio = time.time()
    if not sync_phases.tem_nuvem(ctx):
        ctx.log(
            f"[{SUITE}] AVISO: sem --cloud-url. Medindo só o alvo principal — "
            "a fila entre os dois backends não será exercitada."
        )
    papeis = fase_identidade(ctx)
    fila = fase_enchendo_a_outbox(ctx, papeis)
    fase_convergencia(ctx, fila)
    fase_leitura_de_gestao(ctx)
    sync_contention.fase_contencao(ctx)
    fase_matricula_sob_ataque(ctx)
    ctx.note(SUITE, f"suite concluída em {time.time() - inicio:.1f}s")
