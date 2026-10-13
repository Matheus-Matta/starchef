"""Onde está o tempo da venda: o fluxo EXATO do PDV desktop, medido por etapa.

O PDV abre o pagamento com `POST /orders/submit/` simulando e conclui com o
mesmo endpoint levando pagamentos e `expected_total`. Este script repete os
dois passos com 1, 10 e 50 itens e separa, em cada requisição:

* cliente  — o tempo que o operador espera (rede + proxy + servidor);
* total    — o tempo DENTRO do Django (`Server-Timing`);
* banco    — quanto disso foi banco, e em quantas consultas;
* app      — o resto: CPU do Python.

`cliente - total` é o caminho (rede, proxy, TLS). Sem dependências externas.

    python loadtest/medir_venda.py --base-url http://127.0.0.1:8012 --repeticoes 10
"""
import argparse
import http.client
import json
import re
import statistics
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse

TIMING = re.compile(r'(\w+);dur=([\d.]+)(?:;desc="(\d+) consultas")?')


class Cliente:
    """Uma conexão só, reaproveitada, como o cliente HTTP do PDV."""

    def __init__(self, base_url):
        url = urlparse(base_url)
        classe = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
        self.conexao = classe(url.netloc, timeout=60)
        self.token = ""
        self.terminal = str(uuid.uuid4())

    def pedir(self, metodo, caminho, corpo=None, query=None):
        caminho = "/api/v1" + caminho + (f"?{urlencode(query)}" if query else "")
        cabecalhos = {"Content-Type": "application/json", "X-Terminal-Id": self.terminal,
                      "X-Terminal-Name": "medir_venda", "Idempotency-Key": str(uuid.uuid4())}
        if self.token:
            cabecalhos["Authorization"] = f"Bearer {self.token}"
        bruto = json.dumps(corpo).encode() if corpo is not None else None
        inicio = time.perf_counter()
        self.conexao.request(metodo, caminho, body=bruto, headers=cabecalhos)
        resposta = self.conexao.getresponse()
        conteudo = resposta.read()
        cliente_ms = (time.perf_counter() - inicio) * 1000
        servidor = {nome: float(dur) for nome, dur, _ in TIMING.findall(resposta.getheader("Server-Timing") or "")}
        consultas = next((int(n) for _, _, n in TIMING.findall(resposta.getheader("Server-Timing") or "") if n), None)
        dados = json.loads(conteudo) if conteudo else {}
        if resposta.status >= 400:
            raise RuntimeError(f"{metodo} {caminho} -> {resposta.status}: {str(dados)[:300]}")
        return dados, {"cliente": cliente_ms, "consultas": consultas, **servidor}


def lista(dados):
    return dados.get("results", dados) if isinstance(dados, dict) else dados


def preparar(cli, usuario, senha):
    sessao, _ = cli.pedir("POST", "/auth/login/", {"username": usuario, "password": senha, "no_cookie": True})
    cli.token = sessao["access"]
    restaurante = lista(cli.pedir("GET", "/restaurants/", query={"page_size": 5})[0])[0]["id"]
    estacoes = lista(cli.pedir("GET", "/cash-stations/", query={"restaurant": restaurante})[0])
    if estacoes:
        try:
            cli.pedir("POST", "/cash-register/open/", {"cash_station": estacoes[0]["id"], "opening_amount": "0"})
        except RuntimeError:
            pass  # já aberto
    produtos = [
        p for p in lista(cli.pedir("GET", "/menu/products/", query={
            "restaurant": restaurante, "is_active": "true", "page_size": 300})[0])
        if p.get("pricing_unit") != "kg" and not p.get("is_weighed") and not p.get("requires_variation")
    ]
    metodos = lista(cli.pedir("GET", "/payments/methods/", query={"restaurant": restaurante})[0])
    dinheiro = next(m for m in metodos if m.get("method_type") == "cash")
    if not produtos:
        raise SystemExit("Nenhum produto por unidade no restaurante semeado.")
    return restaurante, produtos, dinheiro["id"]


def venda(cli, restaurante, produtos, dinheiro, itens):
    corpo = {
        "id": str(uuid.uuid4()), "order_type": "counter", "restaurant": restaurante,
        "items": [{"id": str(uuid.uuid4()), "product": produtos[n % len(produtos)]["id"], "quantity": 1}
                  for n in range(itens)],
        "close": {"discount": 0},
    }
    previa, simular = cli.pedir("POST", "/orders/submit/", {**corpo, "simular": True, "payments": []})
    total = previa["order"]["total"]
    pagamento = {"id": str(uuid.uuid4()), "payment_method": dinheiro, "amount": str(total),
                 "client_updated_at": datetime.now(timezone.utc).isoformat()}
    # Como o PDV: a conclusão leva a cozinha junto (`OrderDraftMaterializer.concluir`).
    _, concluir = cli.pedir("POST", "/orders/submit/", {
        **corpo, "payments": [pagamento], "expected_total": total,
        "kitchen": {"client_batch_serial": uuid.uuid4().hex[:12]}})
    return simular, concluir


def resumo(rotulo, medidas):
    def p(campo, q):
        valores = sorted(m[campo] for m in medidas if m.get(campo) is not None)
        if not valores:
            return "   -  "
        return f"{valores[min(len(valores) - 1, int(q * len(valores)))]:6.0f}"

    consultas = statistics.median(m["consultas"] for m in medidas if m.get("consultas") is not None) \
        if any(m.get("consultas") for m in medidas) else 0
    caminho = [m["cliente"] - m.get("total", 0) for m in medidas]
    print(f"{rotulo:<22} cliente p50 {p('cliente', .5)} p95 {p('cliente', .95)} | django {p('total', .5)} "
          f"| banco {p('db', .5)} ({consultas:.0f} consultas) | app {p('app', .5)} "
          f"| caminho {statistics.median(caminho):6.0f}  (ms)")


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--base-url", default="http://127.0.0.1:8012")
    args.add_argument("--usuario", default="admin")
    args.add_argument("--senha", default="admin12345")
    args.add_argument("--repeticoes", type=int, default=10)
    args.add_argument("--itens", default="1,10,50")
    opcoes = args.parse_args()
    cli = Cliente(opcoes.base_url)
    restaurante, produtos, dinheiro = preparar(cli, opcoes.usuario, opcoes.senha)
    print(f"alvo {opcoes.base_url} | {len(produtos)} produtos | {opcoes.repeticoes} vendas por tamanho\n")
    for itens in (int(n) for n in opcoes.itens.split(",")):
        venda(cli, restaurante, produtos, dinheiro, itens)  # aquece
        medidas = [venda(cli, restaurante, produtos, dinheiro, itens) for _ in range(opcoes.repeticoes)]
        resumo(f"{itens:>2} itens  simular", [s for s, _ in medidas])
        resumo(f"{itens:>2} itens  concluir", [c for _, c in medidas])


if __name__ == "__main__":
    main()
