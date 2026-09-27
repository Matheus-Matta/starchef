#!/usr/bin/env python
"""Valida a SINCRONIZAÇÃO dos recursos novos entre a nuvem e a loja.

    bash loadtest/scripts/start_sync_pair.sh
    .venv/Scripts/python loadtest/validar_sync_par.py

O que ele responde é a pergunta que a suíte `sync` não responde. Ela mede a FILA
— vazão, contenção do bilhete de matrícula — contra um alvo só, no papel de
nuvem. Isto aqui pergunta outra coisa:

    **o registro que nasceu num lado aparece no outro?**

São DOIS bancos separados, e é isso que dá valor ao "não existia e passou a
existir". Com um banco só, o que a loja "recebeu" seria a mesma linha que a nuvem
acabou de gravar, e a validação passaria sem provar nada.

As duas direções são medidas porque elas têm regras DIFERENTES no catálogo:

  nuvem → loja   tabela de desconto, regra, vínculo do encarte, cupom e a
                 exigência do código do operador. `cloud_to_local` não é
                 economia de tráfego: é o que impede uma loja de inventar
                 desconto próprio.

  loja → nuvem   o RESGATE do cupom e os `metafields` do pedido. O resgate nasce
                 no pagamento, e o pagamento acontece na loja: sem ele subir, um
                 cupom de uso único usado no balcão fica invisível para a nuvem e
                 a mesma pessoa usa de novo no delivery.
"""
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "loadtest"))

NUVEM = "http://127.0.0.1:8021"
LOJA = "http://127.0.0.1:8022"
USUARIO = "admin"
SENHA = "admin12345"
MARCA = f"SYNCPAR-{uuid.uuid4().hex[:6]}"

#: Quanto esperar um registro atravessar. O worker roda com `--interval 2`, então
#: 60s é folga de sobra — e um teto existe para a validação FALHAR em vez de
#: pendurar quando a ponte está quebrada.
ESPERA_MAX = 60

falhas = []
passos = []


def diga(texto):
    print(texto, flush=True)


def confira(nome, passou, detalhe=""):
    marca = "ok   " if passou else "FALHOU"
    diga(f"  [{marca}] {nome}" + (f" — {detalhe}" if detalhe else ""))
    passos.append((nome, passou, detalhe))
    if not passou:
        falhas.append(nome)


def _requisicao(base, rota, *, token=None, corpo=None, metodo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    pedido = urllib.request.Request(
        f"{base}{rota}",
        data=dados,
        method=metodo or ("POST" if dados else "GET"),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:
            texto = resposta.read().decode()
            return resposta.status, (json.loads(texto) if texto else {})
    except urllib.error.HTTPError as erro:
        texto = erro.read().decode()
        try:
            return erro.code, json.loads(texto) if texto else {}
        except json.JSONDecodeError:
            return erro.code, {"raw": texto[:300]}
    except Exception as erro:  # noqa: BLE001 — rede caída tem de explicar
        return 0, {"raw": str(erro)}


def entrar(base, rotulo, limite=180):
    """Autentica, esperando a CARGA TOTAL quando o par acabou de subir.

    Numa loja recém-matriculada o usuário existe antes do perfil dele: a
    matrícula cria a conta como esqueleto e a carga total traz o resto. Nesse
    intervalo o login responde 401 `account_required` — que não é credencial
    errada, é a carga ainda andando. Desistir no primeiro 401 fazia o validador
    reprovar a ponte justamente enquanto ela funcionava.
    """
    inicio = time.time()
    status, corpo = 0, {}
    while time.time() - inicio < limite:
        status, corpo = _requisicao(base, "/api/v1/auth/login/",
                                    corpo={"username": USUARIO, "password": SENHA})
        token = corpo.get("access") or corpo.get("token")
        if status == 200 and token:
            espera = time.time() - inicio
            diga(f"  sessao ativa em {rotulo}"
                 + (f" (a carga total levou {espera:.0f}s)" if espera > 3 else ""))
            return token
        codigo = ((corpo.get("error") or {}).get("message") or {})
        codigo = codigo.get("code") if isinstance(codigo, dict) else None
        if status == 401 and codigo == "account_required":
            time.sleep(3)
            continue
        break
    diga(f"NAO AUTENTICOU em {rotulo} ({base}): HTTP {status} {corpo}")
    sys.exit(2)


def esperar(base, token, rota, achou, *, rotulo, limite=ESPERA_MAX):
    """Repete a consulta até `achou(corpo)` ou o tempo acabar.

    Devolve `(ok, segundos, ultimo_corpo)`. O tempo volta junto porque ele é a
    informação útil quando passa: "chegou em 4s" diz que a ponte está viva;
    "chegou em 58s" diz que ela está no limite.
    """
    inicio = time.time()
    corpo = {}
    while time.time() - inicio < limite:
        _status, corpo = _requisicao(base, rota, token=token)
        if achou(corpo):
            return True, time.time() - inicio, corpo
        time.sleep(2)
    diga(f"       (tempo esgotado esperando {rotulo})")
    return False, time.time() - inicio, corpo


def _linhas(corpo):
    if isinstance(corpo, dict):
        return corpo.get("results") or corpo.get("data") or []
    return corpo if isinstance(corpo, list) else []


def _por_nome(corpo, trecho, campo="name"):
    return [x for x in _linhas(corpo) if trecho in str(x.get(campo, ""))]


# ──────────────────────────────── nuvem → loja

def criar_na_nuvem(token):
    """Tabela, regra com o "de/por" do encarte, e um cupom. Todos marcados."""
    diga("\n[1/4] criando na NUVEM")
    status, tabela = _requisicao(
        NUVEM, "/api/v1/promotions/discount-tables/", token=token,
        corpo={"name": f"{MARCA} tabela", "is_enabled": True})
    if status not in (200, 201):
        diga(f"NAO CRIOU a tabela: HTTP {status} {tabela}")
        sys.exit(2)

    status, produtos = _requisicao(NUVEM, "/api/v1/menu/products/?page_size=1", token=token)
    alvo = (_linhas(produtos) or [{}])[0]
    if not alvo.get("id"):
        diga("a nuvem nao tem produto — o seed_demo falhou?")
        sys.exit(2)

    status, regra = _requisicao(
        NUVEM, "/api/v1/promotions/rules/", token=token,
        corpo={"table": tabela["id"], "name": f"{MARCA} encarte", "position": 1,
               "target_type": "products", "discount_kind": "fixed",
               "discount_value": "0",
               "product_links": [{"product": alvo["id"],
                                  "promotional_price": "7.77",
                                  "compare_at_price": "99.99"}]})
    if status not in (200, 201):
        diga(f"NAO CRIOU a regra: HTTP {status} {regra}")
        sys.exit(2)

    codigo = f"SP{MARCA.split('-')[1].upper()}"
    status, cupom = _requisicao(
        NUVEM, "/api/v1/promotions/coupons/", token=token,
        corpo={"code": codigo, "discount_kind": "amount", "discount_value": "4.00",
               "name": f"{MARCA} cupom", "single_use_per_customer": True})
    if status not in (200, 201):
        diga(f"NAO CRIOU o cupom: HTTP {status} {cupom}")
        sys.exit(2)

    # A exigência do código do operador é CAMPO do restaurante: ela viaja com ele,
    # e é o que o app do garçom lê da sessão para saber se deve pedir o número.
    status, restaurantes = _requisicao(NUVEM, "/api/v1/restaurants/?page_size=1", token=token)
    restaurante = (_linhas(restaurantes) or [{}])[0]
    # Duas chaves do restaurante, e as duas descem pelo mesmo caminho:
    #
    #   `require_operator_code` e o que esta sob teste.
    #   `require_open_cash_register` e PRE-CONDICAO: a loja precisa RECEBER o
    #   pagamento para o resgate do cupom nascer, e a semente nao cria estacao de
    #   caixa nenhuma. Desligar na NUVEM (e nao na loja) e o certo: o campo
    #   sincroniza `cloud_to_local`, e um PATCH na loja seria sobrescrito na
    #   proxima descida. De quebra, prova um segundo campo atravessando.
    _requisicao(NUVEM, f"/api/v1/restaurants/{restaurante['id']}/", token=token,
                corpo={"require_operator_code": True,
                       "require_open_cash_register": False}, metodo="PATCH")

    diga(f"  tabela, regra (de 99,99 por 7,77) e cupom {codigo} criados")
    return {"tabela": tabela["id"], "regra": regra["id"], "cupom": codigo,
            "produto": alvo["id"], "restaurante": restaurante["id"]}


def conferir_na_loja(token, criado):
    """O que desceu, e se desceu COMPLETO."""
    diga("\n[2/4] conferindo na LOJA (nuvem -> loja)")

    ok, seg, corpo = esperar(
        LOJA, token, "/api/v1/promotions/discount-tables/?page_size=100",
        lambda c: bool(_por_nome(c, MARCA)), rotulo="a tabela de desconto")
    confira("a tabela de desconto desceu", ok, f"{seg:.0f}s")

    ok, seg, corpo = esperar(
        LOJA, token, "/api/v1/promotions/rules/?page_size=100",
        lambda c: bool(_por_nome(c, MARCA)), rotulo="a regra")
    confira("a regra de desconto desceu", ok, f"{seg:.0f}s")

    # O VÍNCULO É O QUE MAIS IMPORTA AQUI. `Promotion.products` está em
    # `exclude_fields` de propósito: ele passa por `PromotionProduct`, que carrega
    # o "de" e o "por". Se só a regra descesse, a promoção chegaria apontando o
    # produto certo com preço vazio — e o caixa da loja cobraria o preço cheio.
    regra = (_por_nome(corpo, MARCA) or [{}])[0]
    vinculos = regra.get("product_links") or []
    confira("o vinculo do encarte desceu com o de/por",
            bool(vinculos) and str(vinculos[0].get("promotional_price")) == "7.77"
            and str(vinculos[0].get("compare_at_price")) == "99.99",
            f"vinculos={vinculos}")

    # A prova final da promoção: o PREÇO que a loja cobra.
    ok, seg, produto = esperar(
        LOJA, token, f"/api/v1/menu/products/{criado['produto']}/",
        lambda c: str(c.get("current_price")) == "7.77", rotulo="o preco na loja")
    confira("a loja passa a cobrar o preco da promocao", ok,
            f"current_price={produto.get('current_price')} "
            f"compare_at={produto.get('compare_at_price')} em {seg:.0f}s")

    ok, seg, corpo = esperar(
        LOJA, token, "/api/v1/promotions/coupons/?page_size=100",
        lambda c: any(x.get("code") == criado["cupom"] for x in _linhas(c)),
        rotulo="o cupom")
    confira("o cupom desceu", ok, f"{seg:.0f}s")

    ok, seg, corpo = esperar(
        LOJA, token, f"/api/v1/restaurants/{criado['restaurante']}/",
        lambda c: c.get("require_operator_code") is True
        and c.get("require_open_cash_register") is False,
        rotulo="as duas chaves do restaurante")
    confira("a exigencia do codigo do operador desceu",
            corpo.get("require_operator_code") is True, f"{seg:.0f}s")
    confira("a configuracao do caixa desceu junto",
            corpo.get("require_open_cash_register") is False,
            f"require_open_cash_register={corpo.get('require_open_cash_register')}")


# ──────────────────────────────── loja → nuvem

def vender_na_loja(token, criado):
    """Uma venda na LOJA: com código do operador, cupom e pagamento.

    É a venda completa de propósito. O resgate do cupom só nasce no PAGAMENTO, e
    os `metafields` só existem se o lançamento os aceitar — cortar caminho aqui
    validaria uma sincronização de registros que a operação real nunca produz.
    """
    diga("\n[3/4] vendendo na LOJA (com codigo do operador e cupom)")
    codigo_operador = "4821"
    status, restaurantes = _requisicao(LOJA, "/api/v1/restaurants/?page_size=1", token=token)
    restaurante = (_linhas(restaurantes) or [{}])[0]

    # O restaurante da loja exige o código — ele desceu assim no passo 2. Abrir
    # sem o número tem de ser recusado, e isso também é a sincronização sendo
    # provada: a REGRA viajou, não só o campo.
    status, _ = _requisicao(
        LOJA, "/api/v1/orders/", token=token,
        corpo={"order_type": "counter", "restaurant": restaurante["id"]})
    confira("a loja recusa abrir pedido sem o codigo do operador",
            status == 400, f"HTTP {status}")

    status, pedido = _requisicao(
        LOJA, "/api/v1/orders/create-with-item/", token=token,
        corpo={"order_type": "counter", "restaurant": restaurante["id"],
               "metafields": {"operator_code": codigo_operador},
               "item": {"product": criado["produto"], "quantity": 2,
                        "metafields": {"operator_code": codigo_operador}}})
    if status not in (200, 201):
        confira("a loja abriu a venda com o codigo", False, f"HTTP {status} {pedido}")
        return None
    confira("a loja abriu a venda com o codigo", True,
            f"pedido #{pedido.get('sequence')}")

    status, fechado = _requisicao(
        LOJA, f"/api/v1/orders/{pedido['id']}/close/", token=token,
        corpo={"service_fee_enabled": False, "fiscal_customer_cpf": "39053344705",
               "coupon_code": criado["cupom"]})
    if status != 200:
        confira("a loja fechou a venda com o cupom", False, f"HTTP {status} {fechado}")
        return None
    confira("a loja fechou a venda com o cupom", True,
            f"desconto {fechado.get('coupon_discount')}")
    confira("a nota da loja mostra o operador com o codigo",
            codigo_operador in str(fechado.get("operator_label") or ""),
            f"operator_label={fechado.get('operator_label')!r}")

    status, metodos = _requisicao(LOJA, "/api/v1/payments/methods/?page_size=50", token=token)
    dinheiro = next((m for m in _linhas(metodos) if m.get("method_type") == "cash"), None)
    if not dinheiro:
        confira("a loja tem forma de pagamento em dinheiro", False, "nenhuma")
        return None
    status, pago = _requisicao(
        LOJA, f"/api/v1/orders/{pedido['id']}/pay/", token=token,
        corpo={"payment_method": dinheiro["id"], "amount": str(fechado["total"])})
    confira("a loja recebeu o pagamento", status in (200, 201), f"HTTP {status}")
    return {"pedido": pedido["id"], "sequence": pedido.get("sequence"),
            "codigo_operador": codigo_operador}


def conferir_na_nuvem(token, criado, venda):
    """O que subiu: o pedido com o rastro, e o RESGATE do cupom."""
    diga("\n[4/4] conferindo na NUVEM (loja -> nuvem)")
    if not venda:
        confira("houve venda na loja para conferir", False, "a venda nao completou")
        return

    ok, seg, corpo = esperar(
        NUVEM, token, f"/api/v1/orders/{venda['pedido']}/",
        lambda c: bool(c.get("id")), rotulo="o pedido da loja")
    confira("o pedido da loja subiu", ok, f"{seg:.0f}s")
    if ok:
        codigo = (corpo.get("metafields") or {}).get("operator_code")
        confira("o codigo do operador subiu junto do pedido",
                str(codigo or "") == venda["codigo_operador"],
                f"metafields.operator_code={codigo!r}")
        confira("a nuvem sabe quem atendeu",
                venda["codigo_operador"] in str(corpo.get("operator_label") or ""),
                f"operator_label={corpo.get('operator_label')!r}")

    # O RESGATE É O QUE MAIS IMPORTA NESTA DIREÇÃO. Sem ele subir, um cupom de uso
    # único usado no balcão fica invisível para a nuvem — e a mesma pessoa usa de
    # novo no delivery, que é atendido pela nuvem.
    ok, seg, corpo = esperar(
        NUVEM, token, "/api/v1/promotions/coupon-redemptions/?page_size=100",
        lambda c: any(str(x.get("coupon_code")) == criado["cupom"] for x in _linhas(c)),
        rotulo="o resgate do cupom")
    confira("o resgate do cupom subiu para a nuvem", ok, f"{seg:.0f}s")

    # E a consequência: a nuvem passa a RECUSAR o mesmo CPF.
    status, restaurantes = _requisicao(NUVEM, "/api/v1/restaurants/?page_size=1", token=token)
    restaurante = (_linhas(restaurantes) or [{}])[0]
    _requisicao(NUVEM, f"/api/v1/restaurants/{restaurante['id']}/", token=token,
                corpo={"require_operator_code": False}, metodo="PATCH")
    status, nova = _requisicao(
        NUVEM, "/api/v1/orders/create-with-item/", token=token,
        corpo={"order_type": "counter", "restaurant": restaurante["id"],
               "item": {"product": criado["produto"], "quantity": 1}})
    if status in (200, 201):
        status, recusa = _requisicao(
            NUVEM, f"/api/v1/orders/{nova['id']}/close/", token=token,
            corpo={"service_fee_enabled": False,
                   "fiscal_customer_cpf": "39053344705",
                   "coupon_code": criado["cupom"]})
        confira("a nuvem recusa o cupom que a loja consumiu",
                status == 422, f"HTTP {status}: "
                f"{(recusa.get('error') or {}).get('message')}")


def main():
    diga(f"marca desta execucao: {MARCA}")
    diga("\nautenticando")
    token_nuvem = entrar(NUVEM, "NUVEM")
    token_loja = entrar(LOJA, "LOJA")

    criado = criar_na_nuvem(token_nuvem)
    conferir_na_loja(token_loja, criado)
    venda = vender_na_loja(token_loja, criado)
    conferir_na_nuvem(token_nuvem, criado, venda)

    diga("")
    diga("=" * 66)
    total = len(passos)
    if falhas:
        diga(f"SINCRONIZACAO COM FALHA: {len(falhas)} de {total} verificacoes")
        for nome in falhas:
            diga(f"  - {nome}")
        return 1
    diga(f"SINCRONIZACAO VALIDADA: {total} de {total} verificacoes passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
