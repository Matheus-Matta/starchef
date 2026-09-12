"""Suite WEB — enxurrada de acessos na retaguarda (SPA Vue).

Pensada como um ataque: conexoes subindo em degraus ate o servidor de estatico
engasgar, com tres cargas misturadas — o shell do SPA, os assets versionados e
as chamadas que a tela dispara ao abrir. No fim, envio de formulario (certo e
errado) enquanto a enxurrada ainda esta acontecendo.
"""
import re
import time

from .. import storm
from ..result import ACCEPT, ANY, REJECT
from ..workers import LoadRunner

SUITE = "web"

ASSET_RE = re.compile(rb"""(?:src|href)=["']([^"']+\.(?:js|css|svg|png|woff2?|ico))["']""")

SPA_ROUTES = [
    "/", "/login", "/dashboard", "/pdv", "/orders", "/customers", "/menu/products",
    "/tables", "/cash-register", "/reports", "/kds", "/rota/que/nao/existe",
]

BOOT_CALLS = [
    ("/api/v1/auth/me/", ACCEPT),
    ("/api/v1/restaurants/?page_size=25", ACCEPT),
    ("/api/v1/menu/products/?page_size=25", ACCEPT),
    ("/api/v1/menu/categories/?page_size=25", ACCEPT),
    ("/api/v1/orders/?page_size=25", ACCEPT),
    ("/api/v1/tables/?page_size=100", ACCEPT),
    ("/api/v1/notifications/unread-count/", ACCEPT),
    ("/api/v1/reports/dashboard/", ACCEPT),
    ("/api/v1/payments/methods/?page_size=50", ACCEPT),
]

#: Sem isto o servidor de estatico trata a requisicao como XHR e devolve 404 no
#: fallback de SPA — a enxurrada mediria a rota errada.
NAVEGADOR = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StarChefLoadTest/1.0",
}

FORM_TARGETS = ["/api/v1/customers/", "/api/v1/menu/products/", "/api/v1/menu/categories/", "/api/v1/tables/"]


def descobrir_assets(ctx):
    """Le o index.html e extrai os arquivos que o navegador buscaria junto."""
    resposta = ctx.web.request("GET", "/", headers=NAVEGADOR)
    if resposta.status != 200:
        ctx.note(SUITE, f"frontend nao respondeu o index ({resposta.status or resposta.error}) — so a API sera atacada")
        return []
    encontrados = [caminho.decode() for caminho in ASSET_RE.findall(resposta.body)]
    assets = [caminho for caminho in encontrados if caminho.startswith("/")]
    ctx.note(SUITE, f"{len(assets)} assets descobertos no index.html")
    return assets[:40]


def _degraus(config):
    """Degraus crescentes e sem repeticao — dois degraus iguais sujariam a media."""
    base = max(2, config.workers)
    passos = [base // 8, base // 4, base // 2, base, base * 2]
    degraus = []
    for passo in passos:
        valor = max(2, passo)
        if not degraus or valor > degraus[-1]:
            degraus.append(valor)
    return degraus


def fase_enxurrada(ctx, assets):
    segundos = max(4, ctx.config.duration // 4)
    ctx.log(f"[{SUITE}] fase 1/3 — enxurrada em degraus ({', '.join(str(d) for d in _degraus(ctx.config))} conexoes)")
    for conexoes in _degraus(ctx.config):
        grupo = f"rampa {conexoes:>4} conexoes"
        runner = LoadRunner(workers=conexoes, duration=segundos)

        def tarefa(worker, iteracao, grupo=grupo, conexoes=conexoes):
            rng = ctx.rng(worker * 977 + iteracao + conexoes)
            sorteio = rng.random()
            if assets and sorteio < 0.45:
                caminho = rng.choice(assets)
            elif sorteio < 0.85:
                caminho = rng.choice(SPA_ROUTES)
            else:
                caminho = f"/assets/inexistente-{rng.randint(1, 9999)}.js"
            inicio = time.time()
            resposta = ctx.web.request("GET", caminho, headers=NAVEGADOR)
            # O SPA devolve o index para qualquer rota; 404 so vale para asset
            # inexistente. Nenhum dos dois pode virar 5xx ou conexao derrubada.
            ctx.record(
                SUITE, grupo, "GET", caminho, resposta,
                expectation=ANY, case="asset" if caminho.startswith("/assets") else "rota_spa", started=inicio,
            )

        runner.run(tarefa)
        stats = ctx.recorder.groups.get(f"{SUITE}::{grupo}")
        if stats:
            resumo = stats.summary()
            ctx.log(f"  {conexoes:>4} conexoes -> {resumo['rps']:7.1f}/s  p99 {resumo['p99_ms']}ms  max {resumo['max_ms']}ms")


def fase_api_de_abertura(ctx):
    segundos = max(4, ctx.config.duration // 4)
    ctx.log(f"[{SUITE}] fase 2/3 — chamadas de abertura de tela ({segundos}s), autenticadas e anonimas")
    runner = LoadRunner(workers=ctx.config.workers, rate=ctx.config.rate, duration=segundos)

    def tarefa(worker, iteracao):
        rng = ctx.rng(worker * 3571 + iteracao)
        caminho, expectativa = rng.choice(BOOT_CALLS)
        anonimo = rng.random() < 0.25
        inicio = time.time()
        if anonimo:
            resposta = ctx.api.request("GET", caminho)
            # Sem credencial a API tem de dizer 401/403 — nunca servir dado.
            ctx.record(SUITE, "api anonima (ataque)", "GET", caminho, resposta,
                       expectation=REJECT, case="sem_credencial", started=inicio)
            return
        resposta = ctx.session.get(caminho)
        ctx.record(SUITE, "api de abertura", "GET", caminho, resposta,
                   expectation=expectativa, case="carga_inicial", started=inicio)

    runner.run(tarefa)


def fase_formularios(ctx):
    segundos = max(4, ctx.config.duration // 4)
    ctx.log(f"[{SUITE}] fase 3/3 — envio de formularios sob carga ({segundos}s), metade preenchida errado")
    alvos = [
        storm.ModelStorm(path.strip("/").replace("api/v1/", ""), path, ctx.schema.for_endpoint("POST", path))
        for path in FORM_TARGETS
    ]
    runner = LoadRunner(workers=ctx.config.workers, rate=ctx.config.rate, duration=segundos)

    def tarefa(worker, iteracao):
        rng = ctx.rng(worker * 6151 + iteracao)
        alvo = rng.choice(alvos)
        if rng.random() < 0.2:
            storm.fire_raw(ctx, SUITE, alvo, rng)
            return
        storm.fire_create(ctx, SUITE, alvo, rng, max(ctx.config.chaos_ratio, 0.5), ctx.config.sloppy_ratio)

    runner.run(tarefa)
    # Uma unica leitura pode pegar a conexao keep-alive que o servidor fechou no
    # fim da rajada; a segunda diz se ele esta de pe de verdade.
    resposta = ctx.web.request("GET", "/", headers=NAVEGADOR)
    if resposta.status not in (200, 304):
        ctx.web.drop()
        resposta = ctx.web.request("GET", "/", headers=NAVEGADOR)
    ctx.check(
        SUITE, "frontend continua servindo o index depois da enxurrada",
        resposta.status in (200, 304), f"HTTP {resposta.status} {resposta.error}".strip(),
    )


def run(ctx):
    inicio = time.time()
    assets = descobrir_assets(ctx)
    fase_enxurrada(ctx, assets)
    fase_api_de_abertura(ctx)
    fase_formularios(ctx)
    ctx.note(SUITE, f"suite concluida em {time.time() - inicio:.1f}s")
