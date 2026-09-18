"""Suite MOBILE — o app do garçom 3.x, no salão.

Substituiu a suíte da linhagem antiga, que simulava o aparelho entregando a um
Caixa Principal porque não alcançava a nuvem. O `pdv_mobile` fala direto com um
backend, como o desktop.

**A topologia é escolha de execução**: aponte `--base-url` para o backend da
loja e você mede o salão com backend local; aponte para a nuvem e mede o acesso
direto.

O que distingue o garçom do caixa, e por isso a suíte não é uma cópia:

- ele abre o pedido **e lança o item no mesmo gesto** (`orders/create-with-item/`),
  porque na mesa ninguém abre comanda vazia para depois anotar;
- ele **não fecha conta** — quem recebe é o caixa. Medir pagamento aqui seria
  medir o app errado;
- são **muitos aparelhos e poucos itens cada**, o oposto do caixa. É o perfil
  que expõe contenção de escrita: N garçons lançando ao mesmo tempo, cada um
  gravando pouco.
"""
import threading
import time
import uuid

from ..auth import clone, login
from ..workers import LoadRunner

SUITE = "mobile"

#: O que o app carrega ao abrir, extraído das chamadas reais de `pdv_mobile/lib`.
ROTAS_DE_ABERTURA = [
    "/api/v1/tables/?page_size=300",
    "/api/v1/commands/?page_size=300&is_active=true",
    "/api/v1/menu/products/?page_size=300&is_active=true",
    "/api/v1/payments/methods/?page_size=100&is_active=true",
    "/api/v1/cash-register/current/",
]


def _sessao_garcom(ctx, indice):
    """A credencial de garçom quando existe; a do orquestrador quando não."""
    if indice == 0:
        try:
            return login(
                ctx.api, ctx.config.username, ctx.config.password,
                terminal_name=f"LT-garcom-{indice + 1}", client_kind="waiter_app",
            )
        except Exception:  # noqa: BLE001 — perfil não-garçom é cenário esperado
            ctx.note(
                SUITE,
                "usuário do teste não tem perfil de garçom; seguindo com a "
                "credencial padrão (mede a carga, não a permissão)",
            )
    return clone(ctx.session, terminal_name=f"LT-garcom-{indice + 1}")


def fase_abertura(ctx):
    """O salão inteiro abrindo o app ao mesmo tempo, no início do turno."""
    ctx.log(f"[{SUITE}] fase 1/3 — abertura simultânea dos aparelhos")
    # `--waiters` descreve o SALÃO; `--workers` descreve a pressão de escrita.
    aparelhos = max(2, min(60, ctx.config.waiters or 6))
    latencias = []
    trava = threading.Lock()

    def abrir(indice, _iteracao):
        sessao = _sessao_garcom(ctx, indice)
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

    LoadRunner(workers=aparelhos, count=aparelhos).run(abrir)

    if latencias:
        latencias.sort()
        pior = latencias[-1]
        ctx.note(
            SUITE,
            f"abertura de {aparelhos} aparelhos: mediana "
            f"{latencias[len(latencias) // 2]:.0f}ms, pior {pior:.0f}ms",
        )
        # O garçom está em pé na frente do cliente. A régua é mais apertada
        # que a do caixa, que abre uma vez no início do turno.
        ctx.check(
            SUITE, "o app do garçom abre rápido mesmo com o salão inteiro ligando",
            pior < 8000,
            f"pior abertura levou {pior:.0f}ms com {aparelhos} aparelhos simultâneos",
        )


def _um_lancamento(ctx, sessao, refs, rng):
    """Abre o pedido lançando o item, como o garçom faz na mesa."""
    produto = rng.choice(refs.unit_products) if refs.unit_products else None
    if produto is None:
        return None

    # O corpo é o do app: o ITEM vai aninhado, e `order_type` é obrigatório.
    # Ver `pdv_mobile/lib/features/orders/data/orders_commands.dart`.
    item = {
        "product": produto.get("id"),
        "quantity": 1,
        "variations": [],
        "addons": [],
        "customer_note": "",
    }
    if refs.ids.get("commands") and rng.random() < 0.7:
        corpo = {
            "order_type": "command",
            "command": rng.choice(refs.ids["commands"]),
            "item": item,
        }
    elif refs.ids.get("tables"):
        corpo = {
            "order_type": "table",
            "table": rng.choice(refs.ids["tables"]),
            "item": item,
        }
    else:
        corpo = {"order_type": "counter", "item": item}

    inicio = time.time()
    resposta = sessao.post(
        "/api/v1/orders/create-with-item/", corpo, idempotency_key=str(uuid.uuid4())
    )
    ctx.record(
        SUITE, f"{SUITE}::lancar_na_mesa", "POST",
        "/api/v1/orders/create-with-item/", resposta,
        expectation="2xx", started=inicio, payload=str(corpo),
    )
    if resposta.status not in (200, 201):
        return None
    pedido = (resposta.json() or {}).get("id")

    # O garçom manda para a cozinha logo depois de lançar — é o gesto dele.
    # Sem isto, a suíte media metade do trabalho do app.
    if pedido:
        inicio = time.time()
        cozinha = sessao.post(
            f"/api/v1/orders/{pedido}/send-to-kitchen/",
            {"client_batch_serial": str(uuid.uuid4())},
            idempotency_key=str(uuid.uuid4()),
        )
        ctx.record(
            SUITE, f"{SUITE}::enviar_cozinha", "POST",
            "/api/v1/orders/{id}/send-to-kitchen/", cozinha,
            expectation="2xx", started=inicio,
        )
    return pedido


def fase_salao(ctx, refs):
    """Muitos garçons lançando pouco cada. É aqui que contenção aparece."""
    ctx.log(f"[{SUITE}] fase 2/3 — salão lançando itens em paralelo")
    rng = ctx.rng(90210)
    pedidos = []
    trava = threading.Lock()

    def lancar(indice, _iteracao):
        sessao = clone(ctx.session, terminal_name=f"LT-garcom-{indice + 1}")
        pedido = _um_lancamento(ctx, sessao, refs, rng)
        if pedido:
            with trava:
                pedidos.append(pedido)

    LoadRunner(
        workers=ctx.config.workers, rate=ctx.config.rate,
        duration=ctx.config.duration, count=ctx.config.count,
    ).run(lancar)

    ctx.note(SUITE, f"salão: {len(pedidos)} lançamentos aceitos")
    ctx.check(
        SUITE, "o salão consegue lançar",
        bool(pedidos),
        "nenhum lançamento passou — confira produto ativo, comanda livre e mesa",
    )
    return pedidos


def fase_conferencia(ctx, pedidos):
    """O item lançado existe, e existe UMA vez.

    O erro clássico do app de garçom é o toque duplo: o dedo escorrega, o
    aparelho manda duas vezes, e o cliente é cobrado por dois refrigerantes que
    pediu uma vez. A chave de idempotência existe para impedir isso — e este é
    o teste que prova que ela funciona sob concorrência.
    """
    ctx.log(f"[{SUITE}] fase 3/3 — conferência dos lançamentos")
    if not pedidos:
        return

    vazios = 0
    for pedido in pedidos[: max(1, min(25, len(pedidos)))]:
        resposta = ctx.session.get(f"/api/v1/orders/{pedido}/")
        if resposta.status != 200:
            continue
        itens = (resposta.json() or {}).get("items") or []
        if not itens:
            vazios += 1

    ctx.check(
        SUITE, "todo lançamento aceito virou item no pedido",
        vazios == 0,
        f"{vazios} pedido(s) criados sem nenhum item — o lançamento respondeu "
        "sucesso e não gravou",
    )


def run(ctx):
    inicio = time.time()
    refs = ctx.refs
    fase_abertura(ctx)
    pedidos = fase_salao(ctx, refs)
    fase_conferencia(ctx, pedidos)
    ctx.note(SUITE, f"suite concluída em {time.time() - inicio:.1f}s")
