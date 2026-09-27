"""A fase do CÓDIGO DO OPERADOR da suíte `promocoes`.

A pergunta é de tudo-ou-nada, e por isso ela é de carga: uma exigência que vale
em 99% das requisições NÃO vale. O 1% que passa é o lançamento sem rastro, e é
justamente nele que a conferência do restaurante vai bater — o item existe, o
cliente consumiu, e ninguém sabe quem anotou.

A fase liga `require_operator_code` no restaurante, mede, e DESLIGA no fim. Deixar
ligado quebraria qualquer suíte que rodasse depois, e o relatório culparia o
lançamento por uma configuração que esta fase deixou para trás.
"""
import threading

from ..auth import clone
from ..workers import LoadRunner

CHAVE = "operator_code"


def _s():
    from . import promocoes

    return promocoes


def _alternar_exigencia(ctx, refs, ligado):
    p = _s()
    restaurante = str((refs.restaurant or {}).get("id", ""))
    resposta = p.chamar(ctx, ctx.session, "config_operador", "PATCH",
                        f"/api/v1/restaurants/{restaurante}/",
                        "/api/v1/restaurants/{id}/",
                        {"require_operator_code": bool(ligado)})
    return resposta.status in (200, 201, 202)


def fase_codigo_do_operador(ctx, refs, cenario):
    """Com a exigência ligada: sem código NUNCA passa; com código, o rastro fica."""
    p = _s()
    ctx.log(f"[{p.SUITE}] fase 6/6 — código do operador, exigido sob carga")
    if not _alternar_exigencia(ctx, refs, True):
        ctx.check(p.SUITE, "a exigência do código pôde ser ligada", False,
                  "o PATCH no restaurante não foi aceito — a fase não mede nada")
        return

    try:
        _medir(ctx, refs, cenario)
    finally:
        # SEMPRE desliga, inclusive se a medição estourar: uma exigência
        # esquecida ligada reprovaria toda suíte que rodasse depois.
        if not _alternar_exigencia(ctx, refs, False):
            ctx.note(p.SUITE, "AVISO: não consegui desligar require_operator_code — "
                              "desligue à mão antes da próxima carga")


def _medir(ctx, refs, cenario):
    p = _s()
    restaurante = str((refs.restaurant or {}).get("id", ""))
    passou_sem_codigo = []
    sem_rastro = []
    com_rastro = 0
    trava = threading.Lock()

    def lancar(worker, iteracao):
        nonlocal com_rastro
        sessao = clone(ctx.session, terminal_name=f"LT-OPER-{worker + 1}")
        # Metade tenta SEM código (tem de ser recusado) e metade COM (tem de
        # gravar). Rodar só um dos dois provaria metade da regra.
        sem_codigo = (worker + iteracao) % 2 == 0
        codigo = "" if sem_codigo else f"{9000 + worker}"

        abertura = p.chamar(
            ctx, sessao, "abrir_conta_operador", "POST", "/api/v1/orders/",
            "/api/v1/orders/",
            {"order_type": "counter", "restaurant": restaurante,
             **({} if sem_codigo else {"metafields": {CHAVE: codigo}})},
            esperado="2xx|400",
        )
        if sem_codigo:
            # A ABERTURA JÁ TEM DE SER BARRADA: o código é pedido antes do
            # primeiro item, e deixar o pedido nascer sem ele criaria um
            # cabeçalho sem rastro que os itens depois herdariam.
            if abertura.status in (200, 201):
                with trava:
                    passou_sem_codigo.append(f"abertura HTTP {abertura.status}")
            return
        if abertura.status not in (200, 201):
            return
        pedido = (abertura.json() or {}).get("id")

        item = p.chamar(ctx, sessao, "lancar_com_codigo", "POST",
                        f"/api/v1/orders/{pedido}/items/",
                        "/api/v1/orders/{id}/items/",
                        {"product": cenario["produto"], "quantity": 1,
                         "variations": [], "addons": [], "customer_note": "",
                         "metafields": {CHAVE: codigo}})
        if item.status not in (200, 201):
            return
        gravado = ((item.json() or {}).get("metafields") or {}).get(CHAVE)
        with trava:
            if str(gravado or "") == codigo:
                com_rastro += 1
            else:
                sem_rastro.append(f"esperado {codigo}, veio {gravado!r}")

    LoadRunner(workers=ctx.config.workers, rate=ctx.config.rate,
               duration=max(4.0, ctx.config.duration / 3)).run(lancar)

    ctx.check(p.SUITE, "sem código o lançamento é recusado SEMPRE",
              not passou_sem_codigo,
              f"{len(passou_sem_codigo)} pedido(s) nasceram sem código "
              f"com a exigência ligada")
    ctx.check(p.SUITE, "o código informado fica gravado no item",
              com_rastro > 0 and not sem_rastro,
              f"{com_rastro} item(ns) com rastro; divergências: "
              f"{sorted(set(sem_rastro))[:3]}")
    # A exigência é do restaurante, e o código é atribuição: qualquer número
    # serve. Letra não — e a recusa tem de ser do CAMPO, não um 500.
    sessao = clone(ctx.session, terminal_name="LT-OPER-LETRA")
    invalido = p.chamar(ctx, sessao, "codigo_com_letra", "POST", "/api/v1/orders/",
                        "/api/v1/orders/",
                        {"order_type": "counter", "restaurant": restaurante,
                         "metafields": {CHAVE: "joao"}},
                        esperado="400")
    ctx.check(p.SUITE, "código com letra é recusado como erro de campo",
              invalido.status == 400,
              f"HTTP {invalido.status}: {p.motivo(invalido)}")
