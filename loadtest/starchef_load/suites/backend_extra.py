"""Fases do BACKEND que a tempestade de CRUD nao alcanca.

Tres frentes que ficavam fora e sao justamente as que mais doem em produ
producao:

- **Relatorios e agregacoes**: leitura pesada, com `GROUP BY`/`SUM` sobre a
  tabela cheia que as fases anteriores acabaram de encher. E onde um indice
  faltando vira segundos de espera, nao milissegundos.
- **Operacoes em lote**: `bulk-create`/`codes-batch` gravam centenas de linhas
  numa transacao so. Um lote grande demais ou um intervalo invertido tem de
  virar 400, nunca 500 nem um lock que segura o banco.
- **Dashboard e posicao de estoque**: as telas de abertura da retaguarda.
"""
import time

from .. import result as verdicts
from ..workers import LoadRunner

SUITE = "backend"

#: Relatorios: (nome, caminho, expectativa). O intervalo de datas e a chave de
#: agrupamento variam por chamada, para nao medir sempre o mesmo plano de query.
RELATORIOS = [
    ("relatorio.vendas", "/api/v1/reports/sales/", verdicts.ACCEPT),
    ("relatorio.pedidos", "/api/v1/reports/orders/", verdicts.ACCEPT),
    ("relatorio.produtos", "/api/v1/reports/products/", verdicts.ACCEPT),
    ("relatorio.pagamentos", "/api/v1/reports/payments/", verdicts.ACCEPT),
    ("relatorio.garcons", "/api/v1/reports/waiters/", verdicts.ACCEPT),
    ("relatorio.restaurantes", "/api/v1/reports/restaurants/", verdicts.ACCEPT),
    ("relatorio.dashboard", "/api/v1/reports/dashboard/", verdicts.ACCEPT),
    ("estoque.posicoes", "/api/v1/stock/positions/", verdicts.ACCEPT),
    ("estoque.alertas", "/api/v1/stock/alerts/", verdicts.ACCEPT),
    ("estoque.validade", "/api/v1/stock/reports/expiry/", verdicts.ACCEPT),
]

#: Janelas de data e filtros que a tela realmente manda — inclusive um par
#: invertido (date_from > date_to) e uma data lixo, que devem dar 400, nao 500.
FILTROS_RELATORIO = [
    "",
    "?date_from=2020-01-01&date_to=2030-12-31",
    "?date_from=2026-01-01&date_to=2026-12-31&group_by=day",
    "?date_from=2026-12-31&date_to=2026-01-01",  # invertido de proposito
    "?date_from=ontem&date_to=amanha",  # lixo
    "?page=1&page_size=100",
    "?page_size=100000",  # page_size absurdo
    "?export=csv",
]


def _restaurante(ctx):
    return str((ctx.refs.restaurant or {}).get("id") or "")


def fase_relatorios(ctx):
    segundos = max(4, ctx.config.duration // 2)
    ctx.log(f"[{SUITE}] fase extra 1/2 — relatorios e agregacoes sob carga ({segundos}s)")
    restaurante = _restaurante(ctx)
    runner = LoadRunner(workers=ctx.config.workers, rate=ctx.config.rate, duration=segundos)

    def tarefa(worker, iteracao):
        rng = ctx.rng(worker * 40503 + iteracao)
        nome, caminho, _ = rng.choice(RELATORIOS)
        filtro = rng.choice(FILTROS_RELATORIO)
        # Filtro invalido pode dar 400 (correto) ou ser ignorado; o que nao
        # pode e estourar 500 nem derrubar a conexao.
        invertido = filtro.startswith("?date_from=2026-12-31")
        expectativa = verdicts.ANY if ("ontem" in filtro or "100000" in filtro or invertido) else verdicts.ACCEPT
        query = filtro
        if restaurante:
            liga = "&" if "?" in query else "?"
            query = f"{query}{liga}restaurant={restaurante}"
        inicio = time.time()
        resposta = ctx.session.get(f"{caminho}{query}")
        ctx.record(
            SUITE, nome, "GET", caminho, resposta,
            expectation=expectativa, case=filtro or "sem_filtro", started=inicio,
        )

    runner.run(tarefa)
    lentos = [
        stats for chave, stats in ctx.recorder.groups.items()
        if chave.startswith(f"{SUITE}::relatorio.") or chave.startswith(f"{SUITE}::estoque.")
    ]
    pior = max((s.summary()["p99_ms"] for s in lentos), default=0)
    ctx.note(SUITE, f"relatorios: p99 mais alto foi {pior} ms")
    if pior > 1000:
        ctx.note(
            SUITE,
            f"ATENCAO: relatorio a {pior} ms no p99 SOB CARGA. Meca um relatorio "
            "isolado (curl): se ele responde em dezenas de ms, o gargalo e a "
            "contencao do servidor de dev (Daphne single-thread agregando em "
            "paralelo), nao a query — reveja com gunicorn + Postgres. Se o "
            "isolado tambem for lento, ai sim procure indice para date_from/"
            "date_to e restaurant.",
        )
    # Uma unica leitura pode pegar a conexao que o Daphne de dev fechou no pico
    # da rajada de agregacao; a segunda diz se o servidor esta de pe de verdade.
    saude = ctx.api.request("GET", "/health/")
    if saude.status != 200:
        ctx.api.drop()
        saude = ctx.api.request("GET", "/health/")
    ctx.check(SUITE, "healthcheck apos os relatorios", saude.status == 200, f"HTTP {saude.status}")


BULK_INVALIDOS = [
    ("intervalo_invertido", {"from_number": 900, "to_number": 100}),
    ("intervalo_gigante", {"from_number": 1, "to_number": 10**9}),
    ("numero_texto", {"from_number": "um", "to_number": "dez"}),
    ("sem_intervalo", {}),
    ("negativo", {"from_number": -50, "to_number": -10}),
]


def fase_lotes(ctx):
    restaurante = _restaurante(ctx)
    if not restaurante:
        ctx.note(SUITE, "sem restaurante: fase de lotes pulada")
        return
    ctx.log(f"[{SUITE}] fase extra 2/2 — operacoes em lote (bulk-create, codes-batch)")
    rng = ctx.rng(999_331)

    # 1) Um lote VALIDO de comandas: cria de verdade, e num intervalo alto para
    #    nao colidir com o que o cenario ja semeou.
    for tentativa in range(max(3, ctx.config.terminals)):
        base = 5000 + tentativa * 500
        corpo = {"restaurant": restaurante, "from_number": base, "to_number": base + 199}
        inicio = time.time()
        resposta = ctx.session.post("/api/v1/commands/bulk-create/", corpo)
        ctx.record(
            SUITE, "lote.comandas", "POST", "/api/v1/commands/bulk-create/", resposta,
            expectation=verdicts.ACCEPT, case="valido", started=inicio,
        )

    # 2) Um lote VALIDO de mesas, se houver um setor.
    setor = ctx.refs.pick("sectors", rng)
    if setor:
        corpo = {"restaurant": restaurante, "sector": setor,
                 "from_number": 8000, "to_number": 8120}
        inicio = time.time()
        resposta = ctx.session.post("/api/v1/tables/bulk-create/", corpo)
        ctx.record(
            SUITE, "lote.mesas", "POST", "/api/v1/tables/bulk-create/", resposta,
            expectation=verdicts.ANY, case="valido", started=inicio,
        )

    # 3) Os invalidos: o limite tem de virar 400, nunca 500 nem lock preso.
    for nome_caso, extra in BULK_INVALIDOS:
        corpo = {"restaurant": restaurante, **extra}
        inicio = time.time()
        resposta = ctx.session.post("/api/v1/commands/bulk-create/", corpo)
        ctx.record(
            SUITE, "lote.comandas (invalido)", "POST", "/api/v1/commands/bulk-create/", resposta,
            expectation=verdicts.REJECT, case=nome_caso, started=inicio,
        )

    # 4) Insumos em lote: `{items: [...]}`, ate 100 por chamada. Um lote acima
    #    do teto e um item sem nome exercitam a validacao.
    lote_valido = {"items": [
        {"name": f"LT Insumo {i}", "unit": "kg"} for i in range(50)
    ]}
    inicio = time.time()
    resposta = ctx.session.post("/api/v1/menu/ingredients/bulk/", lote_valido)
    ctx.record(
        SUITE, "lote.insumos", "POST", "/api/v1/menu/ingredients/bulk/", resposta,
        expectation=verdicts.ANY, case="valido", started=inicio,
    )
    lote_grande = {"items": [{"name": f"X{i}", "unit": "kg"} for i in range(500)]}
    inicio = time.time()
    resposta = ctx.session.post("/api/v1/menu/ingredients/bulk/", lote_grande)
    ctx.record(
        SUITE, "lote.insumos (invalido)", "POST", "/api/v1/menu/ingredients/bulk/", resposta,
        expectation=verdicts.REJECT, case="acima_do_teto", started=inicio,
    )

    saude = ctx.api.request("GET", "/health/")
    ctx.check(SUITE, "healthcheck apos os lotes", saude.status == 200, f"HTTP {saude.status}")


def run(ctx):
    fase_relatorios(ctx)
    fase_lotes(ctx)
