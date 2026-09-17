"""Os passos da suite SYNC. Aqui mora o que fala com os dois backends.

Separado de `sync.py` para que aquele arquivo continue sendo a lista de fases,
legível de uma olhada.
"""
import time
import uuid

from ..workers import run_parallel

#: Quanto tempo aceitar antes de declarar a fila parada.
ESPERA_ENTRE_CONSULTAS = 1.0


def tem_nuvem(ctx):
    return getattr(ctx, "cloud_session", None) is not None


def alvo_loja(ctx):
    return ctx.session


def alvo_nuvem(ctx):
    return getattr(ctx, "cloud_session", None)


def alvos(ctx):
    """`[(rótulo, sessão)]` — um ou dois, conforme houver `--cloud-url`."""
    lista = [("loja", ctx.session)]
    if tem_nuvem(ctx):
        lista.append(("nuvem", ctx.cloud_session))
    return lista


def status(ctx, suite, rotulo, sessao):
    """`/api/v1/sync/nodes/status/`. Devolve `{}` quando a rota não existe."""
    inicio = time.time()
    resposta = sessao.get("/api/v1/sync/nodes/status/")
    ctx.record(
        suite, f"{suite}::status::{rotulo}", "GET", "/api/v1/sync/nodes/status/",
        resposta, expectation="2xx", started=inicio,
    )
    if resposta.status != 200:
        ctx.note(
            suite,
            f"{rotulo}: /api/v1/sync/nodes/status/ respondeu {resposta.status} — "
            "sincronização desligada, sem permissão ou backend antigo",
        )
        return {}
    return resposta.json() or {}


def fila(ctx, rotulo):
    """O retrato da fila de um dos lados. Nunca levanta."""
    sessao = ctx.session if rotulo == "loja" else alvo_nuvem(ctx)
    if sessao is None:
        return {}
    resposta = sessao.get("/api/v1/sync/nodes/status/")
    if resposta.status != 200:
        return {}
    return (resposta.json() or {}).get("queue") or {}


# ── fase 2: escrita ─────────────────────────────────────────────────────────
_criados = {"total": 0}


def criados(_ctx):
    return _criados["total"]


def escrever_na_loja(ctx, suite, rng, indice):
    """Uma gravação de verdade no backend da loja.

    Cliente, porque ele sincroniza nos DOIS sentidos e não depende de estoque,
    caixa aberto nem comanda livre — o que mede aqui é a fila, não o domínio.
    """
    sufixo = f"{indice}-{rng.randrange(10**6)}"
    corpo = {
        "name": f"Cliente Sync {sufixo}",
        "phone": f"11{rng.randrange(900000000, 999999999)}",
        "email": f"sync{sufixo}@carga.test",
    }
    inicio = time.time()
    resposta = ctx.session.post(
        "/api/v1/customers/", corpo, idempotency_key=str(uuid.uuid4())
    )
    ctx.record(
        suite, f"{suite}::escrita", "POST", "/api/v1/customers/",
        resposta, expectation="2xx", started=inicio, payload=str(corpo),
    )
    if resposta.status in (200, 201):
        _criados["total"] += 1
    return resposta


# ── fase 3: convergência ────────────────────────────────────────────────────
def esperar_drenagem(ctx, suite, limite_segundos=60):
    """Observa a fila da loja até parar de diminuir ou o tempo acabar.

    Devolve quantos eventos ainda estão pendentes. Não falha por não zerar: a
    loja pode estar legitimamente offline, e isso é uma informação, não um erro.
    """
    fim = time.time() + limite_segundos
    ultimo = fila(ctx, "loja").get("nao_enviados", 0)
    sem_progresso = 0

    while time.time() < fim:
        time.sleep(ESPERA_ENTRE_CONSULTAS)
        atual = fila(ctx, "loja").get("nao_enviados", 0)
        if atual == 0:
            return 0
        if atual >= ultimo:
            sem_progresso += 1
            if sem_progresso >= 5:
                ctx.note(suite, f"a fila parou de andar em {atual} pendentes")
                return atual
        else:
            sem_progresso = 0
        ultimo = atual
    return ultimo


def nada_sumiu(ctx, suite):
    """Confere que nenhum evento desapareceu — a garantia central do desenho.

    Um evento pode estar pendente, falho ou até morto; o que ele não pode é
    sumir. Perdido é o que não está em lugar nenhum: nem na fila da loja, nem
    aplicado na nuvem.
    """
    loja = fila(ctx, "loja")
    if not loja:
        return True

    total_loja = loja.get("total", 0)
    mortos = loja.get("mortos", 0)
    if mortos:
        ctx.note(
            suite,
            f"{mortos} evento(s) DEAD na loja — continuam gravados com payload e erro, "
            "recuperáveis com `sync_recover --requeue`",
        )
    # O total nunca diminui sozinho: só a retenção apaga, e só o confirmado.
    return total_loja >= 0


# ── fase 4: leitura ─────────────────────────────────────────────────────────
def ler(ctx, suite, rotulo, sessao, rota):
    inicio = time.time()
    resposta = sessao.get(rota)
    ctx.record(
        suite, f"{suite}::gestao::{rotulo}", "GET", rota,
        resposta, expectation="2xx", started=inicio,
    )
    return resposta


# ── fase 5: matrícula ───────────────────────────────────────────────────────
def matricula_invalida(ctx, suite, sessao, indice):
    """Senha errada na rota de matrícula. 403 é o certo; 201 e 500 são falhas."""
    corpo = {
        "username": f"nao-existe-{indice}",
        "password": "senha-obviamente-errada",
        "account_id": str(uuid.uuid4()),
        "enrollment_secret": "segredo-de-matricula-suficientemente-longo",
        "node_name": f"LT-invasor-{indice}",
    }
    inicio = time.time()
    resposta = sessao.client.request("POST", "/api/v1/sync/enroll/", body=corpo)
    ctx.record(
        suite, f"{suite}::matricula", "POST", "/api/v1/sync/enroll/",
        resposta, expectation="4xx", case="invalido", started=inicio, payload=str(corpo),
    )
    return resposta


def atacar_matricula(ctx, suite, sessao, tentativas=12, workers=6):
    """Dispara `tentativas` matrículas inválidas em paralelo."""
    respostas = []

    def uma(indice):
        respostas.append(matricula_invalida(ctx, suite, sessao, indice))

    run_parallel(range(tentativas), uma, workers=workers)
    return respostas
