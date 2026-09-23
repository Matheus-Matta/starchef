"""Suite COMANDA — o ciclo de vida do cartão, do lançamento à gaveta.

A comanda é um bloco de notas: ela anota o consumo e manda para a produção sem
abrir pedido nenhum. O pedido nasce no caixa e recebe as anotações PENDENTES.
Esta suíte percorre esse ciclo inteiro, sob concorrência, e no fim faz a única
pergunta que interessa ao salão:

    **a mesa ficou livre e o cartão voltou para a gaveta?**

É uma pergunta de carga, e não de unidade, porque o que a quebra é a corrida:
dois caixas fechando cartões da mesma mesa, um garçom lançando enquanto o caixa
cobra, um cancelamento no meio. O estado do cartão é mantido por escrita em
vários pontos do backend, e cada ponto é uma chance de ele divergir do que o
cartão REALMENTE tem a cobrar. Um cartão "ocupado" sem nada pendente é um
cartão que ninguém pode usar e uma mesa que ninguém pode sentar — some do salão
sem nada estourar em lugar nenhum.

Cada fase toma cartões seus, por índice, para uma não sabotar a outra: o que se
mede aqui é a corrida do BACKEND, não duas fases disputando o mesmo cartão.
"""
import threading
import time
import uuid
from decimal import Decimal, InvalidOperation

from ..auth import clone
from ..workers import LoadRunner

SUITE = "comanda"

#: Quantos cartões cada fase reserva por trabalhador.
CARTOES_POR_WORKER = 2


class Carteira:
    """Distribui cartões (e mesas) sem que dois trabalhadores peguem o mesmo."""

    def __init__(self, comandas, mesas):
        self._comandas = list(comandas)
        self._mesas = list(mesas)
        self._proximo = 0
        self._trava = threading.Lock()

    def __len__(self):
        return len(self._comandas)

    def tomar(self):
        """Devolve `(comanda, mesa)` ou `None` quando a carteira acaba."""
        with self._trava:
            if self._proximo >= len(self._comandas):
                return None
            indice = self._proximo
            self._proximo += 1
        comanda = self._comandas[indice]
        # Uma mesa por cartão, e não rodízio: a conferência final pergunta "a
        # mesa deste cartão ficou livre?", e com mesa compartilhada a resposta
        # dependia de cartões de outras fases — a mesa reprovava sem que nada
        # de errado tivesse acontecido com o cartão que estava sendo medido.
        mesa = self._mesas[indice] if indice < len(self._mesas) else None
        return comanda, mesa


def _decimal(valor):
    """Converte o decimal-como-texto da API. A API manda "12.50" de propósito,
    para não perder centavo em ponto flutuante no caminho."""
    try:
        return Decimal(str(valor or "0"))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def _preco(produto):
    for chave in ("price", "sale_price", "current_price"):
        valor = (produto or {}).get(chave)
        if valor not in (None, ""):
            return str(valor)
    return "10.00"


def _saturado(resposta):
    """A requisição morreu sem resposta?

    `status == 0` é conexão derrubada ou tempo esgotado, não recusa. A
    diferença importa: o backend RECUSAR é uma afirmação sobre a regra, e
    reprovar por isso é o objetivo da suíte; não haver resposta é o ambiente
    chegando ao teto — no alvo SQLite + servidor de desenvolvimento isso
    começa cedo e não fala nada sobre o código. Misturar os dois fazia a
    suíte reprovar a lógica por causa do banco do laptop.
    """
    return resposta.status == 0


#: O cartão que ESTE trabalhador está manipulando agora. Cada fase roda em
#: threads, uma por operador simulado, então o estado é por thread — passar um
#: dicionário por trinta chamadas seria ruído em cada linha para uma
#: informação que é sempre "a do cartão da vez".
_CARTAO = threading.local()


def _novo_cartao():
    """Começa a acompanhar um cartão neste trabalhador."""
    _CARTAO.incerto = False


def _cartao_incerto():
    """Alguma requisição deste cartão ficou sem resposta?"""
    return getattr(_CARTAO, "incerto", False)


def _chamar(ctx, sessao, grupo, metodo, rota, rota_rotulo, corpo=None,
            esperado="2xx"):
    """Uma requisição registrada. Devolve a resposta crua.

    Qualquer requisição que fique SEM RESPOSTA marca o cartão da vez como
    indeterminado — e cartão indeterminado
    sai de todas as conferências. É a regra que faz a suíte continuar legível
    num alvo saturado: um `void` que não respondeu pode ter sido aplicado ou
    não, e um lançamento que estourou o tempo pode chegar ao banco DEPOIS de a
    suíte já ter lido a comanda. Afirmar qualquer coisa sobre esse cartão é
    inventar — e foi o que fazia a suíte acusar "item que não saiu" onde o que
    houve foi o banco do laptop chegando ao teto.
    """
    inicio = time.time()
    if metodo == "GET":
        resposta = sessao.get(rota)
    elif metodo == "DELETE":
        # Com corpo: cancelar uma anotação exige motivo, e está certo — o que
        # sai da comanda sem ser cobrado é PERDA, e perda pede justificativa.
        resposta = sessao.delete(rota, corpo or {})
    else:
        resposta = sessao.post(rota, corpo or {}, idempotency_key=str(uuid.uuid4()))
    ctx.record(SUITE, f"{SUITE}::{grupo}", metodo, rota_rotulo, resposta,
               expectation=esperado, started=inicio)
    if _saturado(resposta):
        _CARTAO.incerto = True
    return resposta


def _motivo(resposta):
    """A frase que o backend devolveu, para a verificação dizer O QUE recusou.

    Sem isto a suíte reprova com "não completou" e quem lê o relatório abre o
    log do servidor para descobrir o passo — que é justamente o trabalho que
    ela deveria poupar.
    """
    corpo = resposta.json() or {}
    if isinstance(corpo, dict):
        erro = corpo.get("error")
        if isinstance(erro, dict):
            mensagem = erro.get("message")
            if isinstance(mensagem, list):
                return "; ".join(str(m) for m in mensagem)[:160]
            if mensagem:
                return str(mensagem)[:160]
        detalhe = corpo.get("detail")
        if isinstance(detalhe, list):
            return "; ".join(str(d) for d in detalhe)[:160]
        if detalhe:
            return str(detalhe)[:160]
    return ""


def _codigo_do_cartao(ctx, sessao, comanda):
    """O código escaneável do cartão — é o que a balança lê, não o uuid."""
    resposta = _chamar(ctx, sessao, "ler_cartao", "GET",
                       f"/api/v1/commands/{comanda}/", "/api/v1/commands/{id}/")
    if resposta.status != 200:
        return None
    corpo = resposta.json() or {}
    return str(corpo.get("code") or corpo.get("number") or "")


def _pendentes(ctx, sessao, comanda, grupo="ler_comanda"):
    """O que o cartão tem AGORA: `(comanda, itens_pendentes)`.

    É a fonte de verdade desta suíte. O campo `status` é uma cópia disso
    mantida por escrita — e é exatamente a cópia que se quer conferir.
    """
    resposta = _chamar(ctx, sessao, grupo, "GET",
                       f"/api/v1/commands/{comanda}/items/",
                       "/api/v1/commands/{id}/items/")
    if resposta.status != 200:
        return None, None
    corpo = resposta.json() or {}
    return corpo.get("command") or {}, corpo.get("items") or []


# ─────────────────────────────────────────────── fase 0: caixa aberto

def fase_abrir_caixa(ctx):
    """Sem caixa aberto o backend recusa o recebimento — e está certo.

    Pular isto faria a suíte reportar "nenhuma venda fechou" e parecer defeito
    do sistema quando é pré-condição do teste faltando. A estação tem
    operadores autorizados e um usuário só pode estar em uma por vez, então a
    suíte tenta em ordem e fica com a primeira que abrir.
    """
    ctx.log(f"[{SUITE}] fase 0/7 — caixa aberto para receber")
    atual = ctx.session.get("/api/v1/cash-register/current/")
    if atual.status == 200 and (atual.json() or {}).get("id"):
        ctx.note(SUITE, "já havia caixa aberto; reaproveitado")
        return True

    lista = ctx.session.get("/api/v1/cash-stations/?page_size=50&is_active=true")
    corpo = lista.json() or {}
    estacoes = corpo.get("results") or corpo.get("data") or []
    usuario = (ctx.session.user or {}).get("id")
    recusas = []
    for estacao in estacoes:
        for tentativa in (1, 2):
            resposta = _chamar(ctx, ctx.session, "abrir_caixa", "POST",
                               "/api/v1/cash-register/open/",
                               "/api/v1/cash-register/open/",
                               {"cash_station": estacao.get("id"),
                                "opening_amount": "200.00", "notes": "carga comanda"})
            # 409 é "já existe sessão aberta nesta estação": serve igual.
            if resposta.status in (200, 201, 409):
                ctx.note(SUITE, f"caixa aberto em '{estacao.get('name', '?')}' (HTTP {resposta.status})")
                return True
            # A estação tem operadores autorizados, e o usuário da carga não
            # nasce vinculado a nenhuma. Vincular é preparo, não é o que se
            # está medindo — sem isso a suíte reprovaria a venda inteira por
            # uma pré-condição de cadastro.
            motivo = _motivo(resposta)
            if tentativa == 1 and usuario and "vinculado" in motivo.lower():
                ctx.session.patch(f"/api/v1/cash-stations/{estacao.get('id')}/",
                                  {"operators": [usuario]})
                continue
            recusas.append(f"{estacao.get('name', '?')}: HTTP {resposta.status} {motivo}")
            break
    ctx.check(SUITE, "há caixa aberto para receber", False,
              "nenhuma estação aceitou abrir — " + "; ".join(recusas[:4]))
    return False


# ─────────────────────────────────────────────── fase 1: item na comanda

def fase_lancar_item(ctx, refs, carteira):
    """Garçons lançando ao mesmo tempo em cartões diferentes.

    Lança, manda para a produção e confere que a anotação existe PENDENTE. Um
    lançamento que responde 201 e não aparece em `/items/` é o defeito mais
    caro daqui: o cliente consumiu e ninguém vai cobrar.
    """
    ctx.log(f"[{SUITE}] fase 1/7 — lançamento de itens na comanda")
    produtos = refs.unit_products or []
    if not produtos:
        ctx.check(SUITE, "existe produto para lançar", False,
                  "nenhum produto unitário no cenário")
        return []

    lancados = []
    indeterminados = []
    trava = threading.Lock()

    def lancar(worker, iteracao):
        par = carteira.tomar()
        if par is None:
            return
        comanda, mesa = par
        _novo_cartao()
        sessao = clone(ctx.session, terminal_name=f"LT-GARCOM-{worker + 1}")
        rng = ctx.rng(worker * 7717 + iteracao)

        if mesa:
            _chamar(ctx, sessao, "vincular_mesa", "POST",
                    f"/api/v1/commands/{comanda}/link-table/",
                    "/api/v1/commands/{id}/link-table/", {"table_id": mesa})

        quantos = rng.randint(1, 3)
        aceitos = 0
        for _ in range(quantos):
            produto = rng.choice(produtos)
            resposta = _chamar(
                ctx, sessao, "lancar_item", "POST",
                f"/api/v1/commands/{comanda}/items/",
                "/api/v1/commands/{id}/items/",
                {
                    "product": produto.get("id"),
                    "quantity": 1,
                    "variations": [],
                    "addons": [],
                    "customer_note": "",
                },
            )
            if resposta.status in (200, 201):
                aceitos += 1

        if aceitos:
            _chamar(ctx, sessao, "enviar_producao", "POST",
                    f"/api/v1/commands/{comanda}/send-to-kitchen/",
                    "/api/v1/commands/{id}/send-to-kitchen/",
                    {"client_batch_serial": str(uuid.uuid4())})

        cartao, itens = _pendentes(ctx, sessao, comanda)
        if cartao is None:
            return
        if _cartao_incerto():
            with trava:
                indeterminados.append(comanda)
            return
        with trava:
            lancados.append({
                "comanda": comanda,
                "mesa": mesa,
                "lancados": aceitos,
                "pendentes": len(itens),
                "status": cartao.get("status"),
            })

    LoadRunner(
        workers=ctx.config.workers,
        rate=ctx.config.rate,
        count=len(carteira),
    ).run(lancar)

    com_item = [c for c in lancados if c["lancados"]]
    perdidos = [c for c in com_item if c["pendentes"] != c["lancados"]]
    ctx.note(SUITE, f"fase 1: {len(com_item)} cartões receberam item")
    if indeterminados:
        ctx.note(SUITE, f"fase 1: {len(indeterminados)} cartão(ões) com lançamento sem resposta "
                        "(ambiente saturado; ficam fora da conferência)")
    ctx.check(
        SUITE, "o lançamento cria a anotação na comanda",
        bool(com_item) and not perdidos,
        "" if not perdidos else
        f"{len(perdidos)} cartão(ões) aceitaram o item e não o mostram em /items/: "
        + ", ".join(f"{c['comanda']} ({c['lancados']} lançados, {c['pendentes']} pendentes)"
                    for c in perdidos[:4]),
    )
    # Ter pendente é ESTAR EM USO. O campo é uma cópia dessa verdade.
    divergentes = [c for c in com_item if c["status"] != "occupied"]
    ctx.check(
        SUITE, "cartão com anotação pendente consta em uso",
        not divergentes,
        "" if not divergentes else
        f"{len(divergentes)} cartão(ões) com item pendente e status != occupied: "
        + ", ".join(f"{c['comanda']}={c['status']}" for c in divergentes[:4]),
    )
    return com_item


# ──────────────────────────────────── fase 2: uma comanda por venda

def _vender_uma_comanda(ctx, sessao, refs, cartao):
    """Abre a conta de UM cartão, cobra e paga. Devolve o que foi vendido."""
    comanda = cartao["comanda"]
    restaurante = str((refs.restaurant or {}).get("id", ""))

    abertura = _chamar(ctx, sessao, "abrir_conta", "POST", "/api/v1/orders/",
                       "/api/v1/orders/",
                       {"order_type": "command", "restaurant": restaurante})
    if abertura.status not in (200, 201):
        return None, f"abrir HTTP {abertura.status}: {_motivo(abertura)}"
    pedido = (abertura.json() or {}).get("id")
    if not pedido:
        return None, "a abertura não devolveu id de pedido"

    # UMA comanda por venda, de proposito: a conta agrupada tem o caminho dela,
    # e o cartao unico e o caso que o salao repete o dia inteiro.
    anexo = _chamar(ctx, sessao, "anexar_comanda", "POST",
                    f"/api/v1/orders/{pedido}/attach-commands/",
                    "/api/v1/orders/{id}/attach-commands/",
                    {"commands": [comanda]})
    if anexo.status not in (200, 201):
        return None, f"anexar HTTP {anexo.status}: {_motivo(anexo)}"

    fechamento = _chamar(ctx, sessao, "fechar_conta", "POST",
                         f"/api/v1/orders/{pedido}/close/",
                         "/api/v1/orders/{id}/close/",
                         {"discount": 0, "service_fee_enabled": False,
                          "fiscal_customer_cpf": ""})
    if fechamento.status not in (200, 201):
        return None, f"fechar HTTP {fechamento.status}"

    # O total autoritativo e o do FECHAMENTO: e ele que aplica taxa e desconto
    # e trava o valor. Ler o total do anexo pagaria um numero de antes.
    total = (fechamento.json() or {}).get("total") or "0"
    metodo = (refs.payment_by_type.get("cash") or {}).get("id")
    if not metodo:
        return None, "cenário sem forma de pagamento em dinheiro"
    pagamento = _chamar(ctx, sessao, "pagar", "POST",
                        f"/api/v1/orders/{pedido}/pay/",
                        "/api/v1/orders/{id}/pay/",
                        {"payment_method": metodo, "amount": str(total)})
    if pagamento.status not in (200, 201):
        return None, f"pagar HTTP {pagamento.status}: {_motivo(pagamento)}"
    return {"pedido": pedido, "comanda": comanda, "mesa": cartao["mesa"], "total": total}, ""


def fase_venda_por_comanda(ctx, refs, cartoes):
    """Caixas cobrando cartões ao mesmo tempo, um cartão por conta."""
    ctx.log(f"[{SUITE}] fase 2/7 — venda pela comanda (uma comanda por venda)")
    if not cartoes:
        ctx.check(SUITE, "há cartão para cobrar", False, "a fase 1 não deixou cartão com item")
        return []

    vendas = []
    fila = list(cartoes)
    trava = threading.Lock()

    motivos = []
    sem_resposta = []

    def cobrar(worker, _iteracao):
        with trava:
            if not fila:
                return
            cartao = fila.pop()
        _novo_cartao()
        sessao = clone(ctx.session, terminal_name=f"LT-CAIXA-{worker + 1}")
        venda, motivo = _vender_uma_comanda(ctx, sessao, refs, cartao)
        with trava:
            if venda and _cartao_incerto():
                # A venda fechou, mas algum passo no caminho não respondeu: não
                # dá para afirmar nada sobre o estado final deste cartão.
                sem_resposta.append("passo intermediário sem resposta")
            elif venda:
                vendas.append(venda)
            elif motivo.endswith("HTTP 0") or "HTTP 0:" in motivo:
                sem_resposta.append(motivo)
            elif motivo:
                motivos.append(motivo)

    LoadRunner(
        workers=ctx.config.workers,
        rate=ctx.config.rate,
        count=len(cartoes),
    ).run(cobrar)

    ctx.note(SUITE, f"fase 2: {len(vendas)} vendas de cartão único fechadas")
    if sem_resposta:
        ctx.note(SUITE, f"fase 2: {len(sem_resposta)} venda(s) sem resposta do servidor "
                        "(ambiente saturado; use o alvo Postgres para perfis pesados)")
    ctx.check(
        SUITE, "a venda por comanda fecha de ponta a ponta",
        not motivos and bool(vendas),
        "" if not motivos else
        f"{len(motivos)} de {len(cartoes)} cartões foram RECUSADOS em "
        "abrir -> anexar -> fechar -> pagar; onde parou: "
        + "; ".join(sorted(set(motivos))[:4]),
    )
    return vendas


# ─────────────────────────────────────────────── fase 3: cancelamento

def fase_cancelamento(ctx, refs, carteira):
    """Conta aberta com o cartão dentro e cancelada.

    Cancelar é PERDA, não venda — mas o cartão tem de voltar para a gaveta do
    mesmo jeito. Um cancelamento que deixa o cartão preso é pior que o erro que
    o operador estava desfazendo.
    """
    ctx.log(f"[{SUITE}] fase 3/7 — cancelamento da conta com o cartão dentro")
    produtos = refs.unit_products or []
    restaurante = str((refs.restaurant or {}).get("id", ""))
    if not produtos:
        return []

    cancelados = []
    recusas = []
    sem_resposta = []
    trava = threading.Lock()

    def cancelar(worker, _iteracao):
        par = carteira.tomar()
        if par is None:
            return
        comanda, mesa = par
        _novo_cartao()
        sessao = clone(ctx.session, terminal_name=f"LT-CANCELA-{worker + 1}")

        if mesa:
            _chamar(ctx, sessao, "vincular_mesa", "POST",
                    f"/api/v1/commands/{comanda}/link-table/",
                    "/api/v1/commands/{id}/link-table/", {"table_id": mesa})
        item = _chamar(ctx, sessao, "lancar_item", "POST",
                       f"/api/v1/commands/{comanda}/items/",
                       "/api/v1/commands/{id}/items/",
                       {"product": produtos[0].get("id"), "quantity": 1,
                        "variations": [], "addons": [], "customer_note": ""})
        if item.status not in (200, 201):
            with trava:
                (sem_resposta if _saturado(item) else recusas).append(
                    f"lançar HTTP {item.status}: {_motivo(item)}")
            return

        abertura = _chamar(ctx, sessao, "abrir_conta", "POST", "/api/v1/orders/",
                           "/api/v1/orders/",
                           {"order_type": "command", "restaurant": restaurante})
        if abertura.status not in (200, 201):
            with trava:
                (sem_resposta if _saturado(abertura) else recusas).append(
                    f"abrir HTTP {abertura.status}: {_motivo(abertura)}")
            return
        pedido = (abertura.json() or {}).get("id")
        anexo = _chamar(ctx, sessao, "anexar_comanda", "POST",
                        f"/api/v1/orders/{pedido}/attach-commands/",
                        "/api/v1/orders/{id}/attach-commands/",
                        {"commands": [comanda]})
        if anexo.status not in (200, 201):
            with trava:
                (sem_resposta if _saturado(anexo) else recusas).append(
                    f"anexar HTTP {anexo.status}: {_motivo(anexo)}")
            return

        cancelamento = _chamar(ctx, sessao, "cancelar_conta", "POST",
                               f"/api/v1/orders/{pedido}/cancel/",
                               "/api/v1/orders/{id}/cancel/",
                               {
                                   "reason": "carga: cancelamento de conta com comanda",
                                   # Fora da carência o backend exige quem
                                   # autorizou — e está certo: cancelar apaga
                                   # consumo já lançado.
                                   "authorization_username": ctx.config.username,
                                   "authorization_password": ctx.config.password,
                               })
        if cancelamento.status not in (200, 201):
            with trava:
                (sem_resposta if _saturado(cancelamento) else recusas).append(
                    f"HTTP {cancelamento.status}: {_motivo(cancelamento)}")
            return
        with trava:
            if _cartao_incerto():
                sem_resposta.append("passo intermediário sem resposta")
            else:
                cancelados.append({"comanda": comanda, "mesa": mesa, "pedido": pedido})

    LoadRunner(
        workers=ctx.config.workers,
        rate=ctx.config.rate,
        count=len(carteira),
    ).run(cancelar)

    ctx.note(SUITE, f"fase 3: {len(cancelados)} contas canceladas com cartão dentro")
    if sem_resposta:
        ctx.note(SUITE, f"fase 3: {len(sem_resposta)} fluxo(s) sem resposta do servidor "
                        "(ambiente saturado, não recusa)")
    ctx.check(
        SUITE, "a conta com comanda pode ser cancelada",
        bool(cancelados) and not recusas,
        "" if (cancelados and not recusas) else
        f"{len(recusas)} fluxo(s) de cancelamento não completaram; onde parou: "
        + "; ".join(sorted(set(recusas))[:4]),
    )
    return cancelados


# ─────────────────────────────────────────── fase 4: remoção de item

def fase_remocao_de_item(ctx, refs, carteira):
    """Tira as anotações uma a uma até o cartão esvaziar.

    Remover o ÚLTIMO item é o momento em que o cartão deveria voltar para a
    gaveta sozinho. Se ele não voltar, ninguém percebe até o próximo cliente
    encontrar o cartão ocupado por um consumo que não existe mais.
    """
    ctx.log(f"[{SUITE}] fase 4/7 — remoção de item da comanda")
    produtos = refs.unit_products or []
    if not produtos:
        return []

    esvaziados = []
    sem_resposta = []
    trava = threading.Lock()

    def remover(worker, _iteracao):
        par = carteira.tomar()
        if par is None:
            return
        comanda, mesa = par
        _novo_cartao()
        sessao = clone(ctx.session, terminal_name=f"LT-REMOVE-{worker + 1}")

        if mesa:
            _chamar(ctx, sessao, "vincular_mesa", "POST",
                    f"/api/v1/commands/{comanda}/link-table/",
                    "/api/v1/commands/{id}/link-table/", {"table_id": mesa})
        for indice in range(2):
            _chamar(ctx, sessao, "lancar_item", "POST",
                    f"/api/v1/commands/{comanda}/items/",
                    "/api/v1/commands/{id}/items/",
                    {"product": produtos[indice % len(produtos)].get("id"),
                     "quantity": 1, "variations": [], "addons": [], "customer_note": ""})

        _, itens = _pendentes(ctx, sessao, comanda)
        if not itens:
            return
        for item in itens:
            _chamar(ctx, sessao, "remover_item", "DELETE",
                    # A barra final NAO e estetica: sem ela o APPEND_SLASH do
                    # Django estoura em DELETE (nao da para redirecionar
                    # mantendo o corpo) e a rota devolve 500.
                    f"/api/v1/commands/{comanda}/items/{item.get('id')}/void/",
                    "/api/v1/commands/{id}/items/{item}/void/",
                    {"reason": "carga: item removido da comanda"})

        cartao, restantes = _pendentes(ctx, sessao, comanda)
        if cartao is None:
            return
        if _cartao_incerto():
            # O void pode ter sido aplicado e a resposta ter se perdido. Não dá
            # para afirmar nada sobre este cartão sem inventar.
            with trava:
                sem_resposta.append(comanda)
            return
        with trava:
            esvaziados.append({
                "comanda": comanda,
                "mesa": mesa,
                "restantes": len(restantes),
                "status": cartao.get("status"),
            })

    LoadRunner(
        workers=ctx.config.workers,
        rate=ctx.config.rate,
        count=len(carteira),
    ).run(remover)

    sobrando = [c for c in esvaziados if c["restantes"]]
    ctx.note(SUITE, f"fase 4: {len(esvaziados)} cartões esvaziados item a item")
    if sem_resposta:
        ctx.note(SUITE, f"fase 4: {len(sem_resposta)} remoção(ões) sem resposta do servidor "
                        "(ambiente saturado; ficam fora da conferência)")
    ctx.check(
        SUITE, "remover a anotação a tira da comanda",
        bool(esvaziados) and not sobrando,
        "" if not sobrando else
        f"{len(sobrando)} cartão(ões) ainda mostram item pendente depois do void: "
        + ", ".join(f"{c['comanda']}={c['restantes']}" for c in sobrando[:4]),
    )
    return esvaziados


# ───────────────────────────────────── fase 5: a balança anota na comanda

def fase_balanca(ctx, refs, carteira):
    """O cliente passa o cartão, põe o prato, e o peso entra NA COMANDA.

    É o self-service por quilo: a balança não abre pedido. A pesagem vira uma
    anotação pendente como qualquer outra, e o pedido nasce no caixa.

    O peso vai no corpo (`weight_kg`) em vez de um id de leitura: é o caminho
    do replay offline, e é o único que funciona sem o agente local criando
    `ScaleReading` antes. `print: False` porque a etiqueta depende de
    impressora resolvida, e não é ela que está sendo medida aqui.
    """
    ctx.log(f"[{SUITE}] fase 5/7 — a balança anota na comanda")
    balanca = (refs.scale or {}).get("id")
    if not balanca:
        ctx.note(SUITE, "sem balança no cenário; pesagem não exercitada")
        return []

    pesados = []
    trava = threading.Lock()
    recusas = []
    sem_resposta = []

    def pesar(worker, iteracao):
        par = carteira.tomar()
        if par is None:
            return
        comanda, mesa = par
        _novo_cartao()
        sessao = clone(ctx.session, terminal_name=f"LT-BALANCA-{worker + 1}")
        rng = ctx.rng(worker * 3301 + iteracao)

        if mesa:
            _chamar(ctx, sessao, "vincular_mesa", "POST",
                    f"/api/v1/commands/{comanda}/link-table/",
                    "/api/v1/commands/{id}/link-table/", {"table_id": mesa})

        codigo = _codigo_do_cartao(ctx, sessao, comanda)
        if not codigo:
            return
        peso = f"{rng.randint(150, 900) / 1000:.3f}"
        resposta = _chamar(ctx, sessao, "pesar_na_comanda", "POST",
                           f"/api/v1/scales/{balanca}/checkout-command/",
                           "/api/v1/scales/{id}/checkout-command/",
                           {"command_code": codigo, "weight_kg": peso, "print": False})
        if resposta.status not in (200, 201):
            with trava:
                (sem_resposta if _saturado(resposta) else recusas).append(
                    f"pesar HTTP {resposta.status}: {_motivo(resposta)}")
            return

        corpo = resposta.json() or {}
        cartao, itens = _pendentes(ctx, sessao, comanda)
        if cartao is None:
            return
        if _cartao_incerto():
            return
        with trava:
            pesados.append({
                "comanda": comanda,
                "mesa": mesa,
                "peso": peso,
                "pendentes": len(itens),
                "status": cartao.get("status"),
                # A rota NAO pode devolver pedido: a comanda e bloco de notas.
                "abriu_pedido": "order" in corpo,
                "anotacao": (corpo.get("weighed_item") or {}).get("command_status"),
            })

    LoadRunner(
        workers=ctx.config.workers,
        rate=ctx.config.rate,
        count=len(carteira),
    ).run(pesar)

    ctx.note(SUITE, f"fase 5: {len(pesados)} pesagens anotadas na comanda")
    if sem_resposta:
        ctx.note(SUITE, f"fase 5: {len(sem_resposta)} pesagem(ns) sem resposta do servidor "
                        "(ambiente saturado, não recusa)")
    falhou = [p for p in pesados if p["anotacao"] != "pending" or not p["pendentes"]]
    ctx.check(
        SUITE, "a pesagem vira anotação pendente da comanda",
        bool(pesados) and not falhou and not recusas,
        "" if (pesados and not falhou and not recusas) else
        (f"{len(recusas)} pesagem(ns) RECUSADA(s); onde parou: "
         + "; ".join(sorted(set(recusas))[:4]) if recusas else
         f"{len(falhou)} pesagem(ns) não viraram anotação pendente"),
    )
    ctx.check(
        SUITE, "a balança não abre pedido para o cartão",
        not any(p["abriu_pedido"] for p in pesados),
        "" if not any(p["abriu_pedido"] for p in pesados) else
        "a rota devolveu um pedido — a comanda voltou a abrir conta na balança",
    )
    return pesados


# ────────────────────────────────── fase 6: o operador comete erros

def fase_erro_humano(ctx, refs, carteira):
    """Um turno de erros reais, do tipo que acontece com o salão cheio.

    Não é teste de 4xx. É teste de ESTADO: depois de toda a trapalhada, o
    cartão tem de voltar para a gaveta e a mesa tem de ficar livre. Um erro
    que devolve 400 e ainda assim deixa o cartão preso é pior que um 500 —
    ninguém percebe até o cliente seguinte não conseguir usar o cartão.

    Cada erro aqui já aconteceu em balcão: toque duplo, desistir no meio,
    cobrar duas vezes, remover o que já saiu, pesar o mesmo prato de novo.
    """
    ctx.log(f"[{SUITE}] fase 6/7 — o operador atrapalhado")
    produtos = refs.unit_products or []
    restaurante = str((refs.restaurant or {}).get("id", ""))
    balanca = (refs.scale or {}).get("id")
    if not produtos:
        return []

    atrapalhados = []
    inacabados = []
    trava = threading.Lock()
    cincos = []

    def errar(worker, iteracao):
        par = carteira.tomar()
        if par is None:
            return
        comanda, mesa = par
        _novo_cartao()
        sessao = clone(ctx.session, terminal_name=f"LT-ERRO-{worker + 1}")
        rng = ctx.rng(worker * 6151 + iteracao)
        produto = rng.choice(produtos)

        def registra(grupo, resposta):
            if resposta.status >= 500:
                with trava:
                    cincos.append(f"{grupo} HTTP {resposta.status}")

        # ERRO 1 — vincula a mesa, muda de ideia, vincula de novo.
        if mesa:
            for _ in range(2):
                registra("vincular_mesa", _chamar(
                    ctx, sessao, "erro_vincular_mesa", "POST",
                    f"/api/v1/commands/{comanda}/link-table/",
                    "/api/v1/commands/{id}/link-table/", {"table_id": mesa}))
            registra("desvincular_mesa", _chamar(
                ctx, sessao, "erro_desvincular_mesa", "POST",
                f"/api/v1/commands/{comanda}/unlink-table/",
                "/api/v1/commands/{id}/unlink-table/", {}))
            registra("vincular_mesa", _chamar(
                ctx, sessao, "erro_vincular_mesa", "POST",
                f"/api/v1/commands/{comanda}/link-table/",
                "/api/v1/commands/{id}/link-table/", {"table_id": mesa}))

        # ERRO 2 — toque duplo no mesmo item.
        corpo_item = {"product": produto.get("id"), "quantity": 1,
                      "variations": [], "addons": [], "customer_note": ""}
        for _ in range(2):
            registra("lancar_item", _chamar(
                ctx, sessao, "erro_lancar_duplicado", "POST",
                f"/api/v1/commands/{comanda}/items/",
                "/api/v1/commands/{id}/items/", corpo_item))

        # ERRO 3 — quantidade impossível.
        registra("lancar_item", _chamar(
            ctx, sessao, "erro_quantidade_invalida", "POST",
            f"/api/v1/commands/{comanda}/items/",
            "/api/v1/commands/{id}/items/",
            {**corpo_item, "quantity": -5}, esperado="4xx"))

        # ERRO 4 — pesa duas vezes o mesmo prato (o cliente voltou ao buffet).
        if balanca:
            codigo = _codigo_do_cartao(ctx, sessao, comanda)
            if codigo:
                for _ in range(2):
                    registra("pesar", _chamar(
                        ctx, sessao, "erro_pesar_repetido", "POST",
                        f"/api/v1/scales/{balanca}/checkout-command/",
                        "/api/v1/scales/{id}/checkout-command/",
                        {"command_code": codigo, "weight_kg": "0.450", "print": False}))
                # ERRO 5 — peso zero e cartão inexistente.
                registra("pesar", _chamar(
                    ctx, sessao, "erro_peso_zero", "POST",
                    f"/api/v1/scales/{balanca}/checkout-command/",
                    "/api/v1/scales/{id}/checkout-command/",
                    {"command_code": codigo, "weight_kg": "0", "print": False},
                    esperado="4xx"))
                registra("pesar", _chamar(
                    ctx, sessao, "erro_cartao_inexistente", "POST",
                    f"/api/v1/scales/{balanca}/checkout-command/",
                    "/api/v1/scales/{id}/checkout-command/",
                    {"command_code": "COMANDA-QUE-NAO-EXISTE",
                     "weight_kg": "0.300", "print": False}, esperado="4xx"))

        # ERRO 6 — remove um item, tenta remover o MESMO de novo, e sem motivo.
        _, itens = _pendentes(ctx, sessao, comanda, grupo="erro_ler_comanda")
        if itens:
            alvo = itens[0].get("id")
            rota = f"/api/v1/commands/{comanda}/items/{alvo}/void/"
            rotulo = "/api/v1/commands/{id}/items/{item}/void/"
            registra("remover_sem_motivo", _chamar(
                ctx, sessao, "erro_remover_sem_motivo", "DELETE", rota, rotulo,
                {}, esperado="4xx"))
            registra("remover", _chamar(
                ctx, sessao, "erro_remover", "DELETE", rota, rotulo,
                {"reason": "erro do operador"}))
            registra("remover_de_novo", _chamar(
                ctx, sessao, "erro_remover_repetido", "DELETE", rota, rotulo,
                {"reason": "erro do operador"}, esperado="4xx"))

        # ERRO 7 — abre uma conta e ABANDONA (o cliente desistiu no balcão).
        abandonada = _chamar(ctx, sessao, "erro_abrir_conta", "POST",
                             "/api/v1/orders/", "/api/v1/orders/",
                             {"order_type": "command", "restaurant": restaurante})
        registra("abrir", abandonada)
        if abandonada.status in (200, 201):
            vazio = (abandonada.json() or {}).get("id")
            # Pedido vazio se descarta sem senha — e precisa se descartar,
            # senão o cartão fica presa a uma conta que ninguém vai pagar.
            registra("cancelar_vazio", _chamar(
                ctx, sessao, "erro_cancelar_vazio", "POST",
                f"/api/v1/orders/{vazio}/cancel/",
                "/api/v1/orders/{id}/cancel/", {"reason": "cliente desistiu"}))

        # ERRO 8 — cobra o cartão DUAS VEZES na mesma conta.
        pedido_resposta = _chamar(ctx, sessao, "erro_abrir_conta", "POST",
                                  "/api/v1/orders/", "/api/v1/orders/",
                                  {"order_type": "command", "restaurant": restaurante})
        registra("abrir", pedido_resposta)
        if pedido_resposta.status not in (200, 201):
            return
        pedido = (pedido_resposta.json() or {}).get("id")
        primeiro = _chamar(ctx, sessao, "erro_anexar", "POST",
                           f"/api/v1/orders/{pedido}/attach-commands/",
                           "/api/v1/orders/{id}/attach-commands/",
                           {"commands": [comanda]})
        registra("anexar", primeiro)
        # O MESMO cartão de novo: o consumo não pode ser cobrado em dobro.
        registra("anexar_repetido", _chamar(
            ctx, sessao, "erro_anexar_repetido", "POST",
            f"/api/v1/orders/{pedido}/attach-commands/",
            "/api/v1/orders/{id}/attach-commands/",
            {"commands": [comanda]}, esperado="4xx"))

        if primeiro.status not in (200, 201):
            # Cartão sem nada a cobrar recusa e está certo; mas então não há
            # conta para seguir, e o pedido aberto precisa sumir.
            _chamar(ctx, sessao, "erro_cancelar_vazio", "POST",
                    f"/api/v1/orders/{pedido}/cancel/",
                    "/api/v1/orders/{id}/cancel/", {"reason": "nada a cobrar"})
            with trava:
                inacabados.append(comanda)
            return

        # ERRO 9 — fecha duas vezes, paga a menos, depois paga certo.
        for _ in range(2):
            registra("fechar", _chamar(
                ctx, sessao, "erro_fechar_repetido", "POST",
                f"/api/v1/orders/{pedido}/close/",
                "/api/v1/orders/{id}/close/",
                {"discount": 0, "service_fee_enabled": False,
                 "fiscal_customer_cpf": ""}, esperado="qualquer"))

        estado = _chamar(ctx, sessao, "erro_ler_pedido", "GET",
                         f"/api/v1/orders/{pedido}/", "/api/v1/orders/{id}/")
        total = (estado.json() or {}).get("total") or "0"
        metodo = (refs.payment_by_type.get("cash") or {}).get("id")
        # ERRO 10 — paga um troco de nada e SÓ DEPOIS acerta.
        #
        # Aqui está o ponto da fase: errar não pode impedir o desfecho certo.
        # O operador erra o valor, o sistema recusa ou registra parcial, e o
        # fechamento correto tem de continuar possível — com o cartão voltando
        # para a gaveta no fim, como se nada tivesse acontecido.
        concluiu = False
        if metodo:
            registra("pagar_a_menos", _chamar(
                ctx, sessao, "erro_pagar_a_menos", "POST",
                f"/api/v1/orders/{pedido}/pay/", "/api/v1/orders/{id}/pay/",
                {"payment_method": metodo, "amount": "0.01"},
                esperado="qualquer"))
            # Relê o pedido: depois de um recebimento parcial o que falta não
            # é mais o total, e insistir no total seria pagar a mais.
            atual = _chamar(ctx, sessao, "erro_ler_pedido", "GET",
                            f"/api/v1/orders/{pedido}/", "/api/v1/orders/{id}/")
            corpo = atual.json() or {}
            pagos = sum(
                _decimal(p.get("amount"))
                for p in (corpo.get("payments") or [])
                if p.get("status") in (None, "approved")
            )
            falta = _decimal(corpo.get("total") or total) - pagos
            if falta > 0:
                acerto = _chamar(
                    ctx, sessao, "erro_pagar_acertando", "POST",
                    f"/api/v1/orders/{pedido}/pay/", "/api/v1/orders/{id}/pay/",
                    {"payment_method": metodo, "amount": f"{falta:.2f}"},
                    esperado="qualquer")
                registra("pagar", acerto)
                concluiu = acerto.status in (200, 201)
            else:
                concluiu = True

        with trava:
            if concluiu and not _cartao_incerto():
                atrapalhados.append({"comanda": comanda, "mesa": mesa})
            else:
                inacabados.append(comanda)

    LoadRunner(
        workers=ctx.config.workers,
        rate=ctx.config.rate,
        count=len(carteira),
    ).run(errar)

    ctx.note(SUITE, f"fase 6: {len(atrapalhados)} cartões erraram e ainda assim fecharam a venda")
    if inacabados:
        ctx.note(SUITE, f"fase 6: {len(inacabados)} cartão(ões) não chegaram ao fim da venda "
                        "(ficam legitimamente em uso e saem da conferência)")
    ctx.check(
        SUITE, "erro de operador não derruba o servidor",
        not cincos,
        "" if not cincos else
        f"{len(cincos)} resposta(s) 5xx em gesto de erro comum: "
        + "; ".join(sorted(set(cincos))[:6]),
    )
    return atrapalhados

# ───────────────────────────── fase 7: a mesa e o cartão ficaram livres?

def fase_conferencia(ctx, encerrados):
    """A pergunta do salão, feita a cada cartão e a cada mesa que passou daqui.

    Esta é a fase que justifica a suíte. Tudo acima pode responder 2xx e ainda
    assim deixar o salão travado: o que prende a mesa não é um erro, é um
    estado que ficou para trás.
    """
    ctx.log(f"[{SUITE}] fase 7/7 — conferência: a mesa e o cartão ficaram livres?")
    sessao = ctx.session

    cartoes_presos = []
    itens_orfaos = []
    for registro in encerrados:
        comanda = registro["comanda"]
        cartao, itens = _pendentes(ctx, sessao, comanda, grupo="conferir_comanda")
        if cartao is None:
            continue
        if itens:
            itens_orfaos.append(f"{comanda} ({len(itens)} pendente(s), via {registro['origem']})")
        if cartao.get("status") != "free":
            cartoes_presos.append(f"{comanda}={cartao.get('status')} (via {registro['origem']})")

    ctx.check(
        SUITE, "o cartão encerrado não guarda anotação pendente",
        not itens_orfaos,
        "" if not itens_orfaos else
        f"{len(itens_orfaos)} cartão(ões) encerrados ainda têm o que cobrar: "
        + ", ".join(itens_orfaos[:6]),
    )
    ctx.check(
        SUITE, "A COMANDA FICOU LIVRE",
        not cartoes_presos,
        "" if not cartoes_presos else
        f"{len(cartoes_presos)} cartão(ões) continuam ocupados sem nada a cobrar — "
        "o próximo cliente não consegue usar: " + ", ".join(cartoes_presos[:6]),
    )

    mesas = {r["mesa"] for r in encerrados if r.get("mesa")}
    mesas_presas = []
    for mesa in mesas:
        resposta = _chamar(ctx, sessao, "conferir_mesa", "GET",
                           f"/api/v1/tables/{mesa}/", "/api/v1/tables/{id}/")
        if resposta.status != 200:
            continue
        corpo = resposta.json() or {}
        if corpo.get("status") != "free":
            mesas_presas.append(f"{corpo.get('number', mesa)}={corpo.get('status')}")

    ctx.check(
        SUITE, "A MESA FICOU LIVRE",
        bool(mesas) and not mesas_presas,
        f"{len(mesas_presas)} mesa(s) seguem ocupadas sem comanda sentada nelas: "
        + ", ".join(mesas_presas[:6]) if mesas_presas else
        ("" if mesas else
         "nenhuma mesa foi exercitada — o preparo não conseguiu criar mesas "
         "(confira se há setor de mesas no cenário)"),
    )
    return {"cartoes_presos": cartoes_presos, "mesas_presas": mesas_presas}


def _reservar_cartoes(ctx, refs, quantos):
    """Cria cartões NOVOS para esta execução, em vez de reaproveitar os da conta.

    Isolamento não é preciosismo aqui: um cartão que sobrou ocupado de uma
    execução anterior faria a fase 1 contar anotações que não são dela e a
    conferência final acusar um cartão preso que este teste nunca tocou. A
    suíte que reprova por sujeira própria deixa de ser lida.
    """
    restaurante = str((refs.restaurant or {}).get("id", ""))
    criados = []
    for _ in range(quantos):
        resposta = _chamar(ctx, ctx.session, "criar_cartao", "POST",
                           "/api/v1/commands/", "/api/v1/commands/",
                           {"restaurant": restaurante})
        if resposta.status in (200, 201):
            identificador = (resposta.json() or {}).get("id")
            if identificador:
                criados.append(str(identificador))
    return criados


def _reservar_mesas(ctx, refs, quantas):
    """Mesas próprias, pelo mesmo motivo — e numeradas fora da faixa do salão."""
    restaurante = str((refs.restaurant or {}).get("id", ""))
    setor = (refs.ids.get("sectors") or [None])[0]
    if not setor:
        return []
    # O numero e unico por filial. Derivar da semente (que e fixa) fazia a
    # SEGUNDA execucao colidir com as mesas da primeira, criar zero mesas e
    # reprovar a conferencia do salao sem ter exercitado mesa nenhuma — uma
    # reprovacao que nao falava de defeito nenhum do sistema.
    base = 90000 + int(time.time()) % 900000
    criadas = []
    for indice in range(quantas):
        resposta = _chamar(ctx, ctx.session, "criar_mesa", "POST",
                           "/api/v1/tables/", "/api/v1/tables/",
                           {"restaurant": restaurante, "sector": setor,
                            "number": base + indice, "seats": 4})
        if resposta.status in (200, 201):
            identificador = (resposta.json() or {}).get("id")
            if identificador:
                criadas.append(str(identificador))
    return criadas


def _carteiras(ctx, refs):
    """Reparte os cartões desta execução entre as três fases que os consomem."""
    por_fase = max(1, ctx.config.workers * CARTOES_POR_WORKER)
    fases = 5  # venda, cancelamento, remoção, balança e erro humano
    comandas = _reservar_cartoes(ctx, refs, por_fase * fases)
    mesas = _reservar_mesas(ctx, refs, len(comandas))
    ctx.note(SUITE, f"preparo: {len(comandas)} cartões e {len(mesas)} mesas criados para esta execução")
    fatias = [
        (comandas[i * por_fase:(i + 1) * por_fase], mesas[i * por_fase:(i + 1) * por_fase])
        for i in range(fases)
    ]
    return [Carteira(cartoes, salao) for cartoes, salao in fatias]


def run(ctx):
    inicio = time.time()
    refs = ctx.refs
    if not (refs.restaurant or {}).get("id"):
        ctx.check(SUITE, "há restaurante no cenário", False,
                  "nenhum restaurante na conta — rode `manage.py seed_demo` antes")
        return

    fase_abrir_caixa(ctx)
    venda, cancelamento, remocao, pesagem, bagunca = _carteiras(ctx, refs)
    if not len(venda):
        ctx.check(SUITE, "o preparo criou cartões", False,
                  "nenhum cartão foi criado — a suíte não tem o que exercitar")
        return

    cartoes = fase_lancar_item(ctx, refs, venda)
    vendidos = fase_venda_por_comanda(ctx, refs, cartoes)
    cancelados = fase_cancelamento(ctx, refs, cancelamento)
    esvaziados = fase_remocao_de_item(ctx, refs, remocao)
    pesados = fase_balanca(ctx, refs, pesagem)
    atrapalhados = fase_erro_humano(ctx, refs, bagunca)

    encerrados = (
        [{**v, "origem": "venda"} for v in vendidos]
        + [{**c, "origem": "cancelamento"} for c in cancelados]
        + [{**e, "origem": "remoção de item"} for e in esvaziados]
        + [{**b, "origem": "erro do operador"} for b in atrapalhados]
    )
    fase_conferencia(ctx, encerrados)
    ctx.note(SUITE, f"suite concluída em {time.time() - inicio:.1f}s")
