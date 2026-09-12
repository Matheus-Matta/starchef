"""Suite BACKEND — tempestade de criacao em todos os modelos da API.

Cinco fases, nesta ordem de proposito: primeiro o modelo isolado (para saber
o teto de CADA um), depois todos misturados (para achar contencao de banco e
lock), depois leitura sob carga, depois corpo cru malformado e por fim
alteracao/exclusao — inclusive de coisas que nunca existiram.
"""
import time

from .. import storm
from ..suites import backend_extra
from ..workers import LoadRunner

SUITE = "backend"


def _storms(ctx):
    modelos = storm.selectable_models(ctx.schema, ctx.config.models)
    colecoes = {path for _, path in modelos}
    return [
        storm.ModelStorm(nome, path, ctx.schema.for_endpoint("POST", path),
                         action=storm.is_action_path(path, colecoes))
        for nome, path in modelos
    ]


def _burst_seconds(config, quantidade):
    """Cada modelo leva a taxa alvo cheia por alguns segundos."""
    if config.count:
        return 0
    return max(2, min(config.duration, config.duration * 4 // max(quantidade, 1) or 2))


def fase_rajada_por_modelo(ctx, storms):
    segundos = _burst_seconds(ctx.config, len(storms))
    ctx.log(f"[{SUITE}] fase 1/5 — rajada isolada: {len(storms)} modelos x {segundos}s a {ctx.config.rate}/s alvo")
    for indice, alvo in enumerate(storms):
        rng = ctx.rng(indice * 101)
        runner = LoadRunner(
            workers=ctx.config.workers, rate=ctx.config.rate,
            duration=segundos, count=ctx.config.count,
        )
        runner.run(lambda _w, _i, alvo=alvo, rng=rng: storm.fire_create(ctx, SUITE, alvo, rng, ctx.config.chaos_ratio, ctx.config.sloppy_ratio))
        if ctx.config.verbose:
            chave = f"{SUITE}::{alvo.name}"
            stats = ctx.recorder.groups.get(chave)
            if stats:
                ctx.log(f"  {alvo.name:38} {stats.total:6} reqs  {stats.rps:7.1f}/s  p99 {stats.summary()['p99_ms']}ms")


def fase_tempestade_misturada(ctx, storms):
    ctx.log(f"[{SUITE}] fase 2/5 — tempestade misturada: {ctx.config.duration}s, todos os modelos ao mesmo tempo")
    runner = LoadRunner(workers=ctx.config.workers, rate=ctx.config.rate, duration=ctx.config.duration)

    def tarefa(worker, iteracao):
        rng = ctx.rng(worker * 7919 + iteracao)
        storm.fire_create(ctx, SUITE, rng.choice(storms), rng, ctx.config.chaos_ratio, ctx.config.sloppy_ratio)

    runner.run(tarefa)


def fase_leitura(ctx, storms):
    segundos = max(3, ctx.config.duration // 3)
    ctx.log(f"[{SUITE}] fase 3/5 — leitura sob carga ({segundos}s): paginacao, busca, delta sync e filtro invalido")
    runner = LoadRunner(workers=ctx.config.workers, rate=ctx.config.rate, duration=segundos)

    def tarefa(worker, iteracao):
        rng = ctx.rng(worker * 104729 + iteracao)
        storm.fire_read(ctx, SUITE, rng.choice(storms), rng)

    runner.run(tarefa)


def fase_corpo_cru(ctx, storms):
    ctx.log(f"[{SUITE}] fase 4/5 — corpos crus malformados (json quebrado, 2 MB, binario, content-type errado)")
    alvos = storms[:12]
    runner = LoadRunner(workers=min(ctx.config.workers, 16), rate=min(ctx.config.rate, 60),
                        count=max(40, len(alvos) * 8))

    def tarefa(worker, iteracao):
        rng = ctx.rng(worker * 31 + iteracao)
        storm.fire_raw(ctx, SUITE, rng.choice(alvos), rng)

    runner.run(tarefa)


def fase_alteracao(ctx, storms):
    segundos = max(3, ctx.config.duration // 3)
    ctx.log(f"[{SUITE}] fase 5/5 — alteracao e exclusao ({segundos}s), com IDs validos e inexistentes")
    com_ids = [s for s in storms if s.created_ids] or storms
    runner = LoadRunner(workers=ctx.config.workers, rate=ctx.config.rate, duration=segundos)

    def tarefa(worker, iteracao):
        rng = ctx.rng(worker * 65537 + iteracao)
        storm.fire_mutate(ctx, SUITE, rng.choice(com_ids), rng, ctx.config.chaos_ratio)

    runner.run(tarefa)


def verificar_coerencia(ctx, storms):
    """Depois da tempestade, a API ainda responde e conta o que criou?"""
    saude = ctx.api.request("GET", "/health/")
    ctx.check(SUITE, "healthcheck apos a carga", saude.status == 200, f"HTTP {saude.status}")
    for alvo in storms[:10]:
        if not alvo.created_ids:
            continue
        identificador = alvo.created_ids[0]
        resposta = ctx.session.get(f"{alvo.path}{identificador}/")
        ctx.check(
            SUITE, f"registro criado continua legivel ({alvo.name})",
            resposta.status in (200, 404),
            f"HTTP {resposta.status}",
        )
        break
    total_criado = sum(len(s.created_ids) for s in storms)
    ctx.note(SUITE, f"{total_criado} registros criados foram rastreados para leitura/alteracao posterior")


def limpar(ctx, storms):
    ctx.log(f"[{SUITE}] limpeza — removendo os registros criados")
    removidos = 0
    for alvo in storms:
        for identificador in list(alvo.created_ids):
            resposta = ctx.session.delete(f"{alvo.path}{identificador}/")
            removidos += 1 if resposta.status in (200, 202, 204) else 0
    ctx.note(SUITE, f"limpeza removeu {removidos} registros")


def run(ctx):
    storms = _storms(ctx)
    if not storms:
        ctx.log(f"[{SUITE}] nenhum modelo selecionado — verifique --models")
        return
    ctx.log(f"[{SUITE}] {len(storms)} modelos no alvo: {', '.join(s.name for s in storms[:12])}...")
    inicio = time.time()
    fase_rajada_por_modelo(ctx, storms)
    fase_tempestade_misturada(ctx, storms)
    fase_leitura(ctx, storms)
    fase_corpo_cru(ctx, storms)
    fase_alteracao(ctx, storms)
    # Fases que a tempestade de CRUD nao alcanca: relatorios/agregacoes sobre a
    # tabela ja cheia, e operacoes em lote. Rodam DEPOIS, de proposito — a
    # agregacao so tem o que medir com dados dentro.
    backend_extra.run(ctx)
    verificar_coerencia(ctx, storms)
    if ctx.config.cleanup:
        limpar(ctx, storms)
    ctx.note(SUITE, f"suite concluida em {time.time() - inicio:.1f}s sobre {len(storms)} modelos")
