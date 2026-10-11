"""200 vendas com NFC-e pela ACBrLib na LOJA do par Docker, como o PDV faz.

Metade com a SEFAZ simulada no ar (autorização direta) e metade com ela fora
(contingência offline: tpEmis=9, assinada agora, transmitida depois). Mais uma
nota com 200 itens. Uso: `python emitir.py <dados.json> <saida.json>`, com o
JSON que `preparar.py` imprimiu.
"""
import json
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

LOJA = "http://127.0.0.1:8022/api/v1"
COMUNICADOR = "http://127.0.0.1:8032"
TOKEN_ACBR = "par-acbr-token"
CAIXAS = 4


def entrar(caixa):
    """Entra como o operador e abre o caixa da estação dele (o pix exige caixa aberto)."""
    resposta = httpx.post(f"{LOJA}/auth/login/",
                          json={"username": caixa["usuario"], "password": "Senha12345!"})
    resposta.raise_for_status()
    corpo = resposta.json()
    token = corpo.get("access") or corpo.get("access_token") or corpo.get("token")
    cliente = httpx.Client(base_url=LOJA, timeout=90, headers={"Authorization": f"Bearer {token}"},
                           cookies=resposta.cookies)
    aberto = cliente.post("/cash-register/open/", json={"cash_station": caixa["estacao"],
                                                         "opening_amount": "100.00"})
    if aberto.status_code not in (200, 201, 409):
        raise RuntimeError(f"abrir caixa: {aberto.status_code} {aberto.text[:200]}")
    return cliente


def sefaz(modo):
    httpx.post(f"{COMUNICADOR}/_simulador/modo", json={"modo": modo},
               headers={"Authorization": f"Bearer {TOKEN_ACBR}"}).raise_for_status()


def _ok(resposta):
    if resposta.status_code >= 400:
        raise RuntimeError(f"{resposta.request.method} {resposta.request.url.path} "
                           f"{resposta.status_code}: {resposta.text[:300]}")
    return resposta.json()


def vender(cliente, dados, itens, fase):
    """Abre o pedido de balcão, lança `itens` itens, recebe no pix e emite."""
    produtos = dados["produtos"]
    inicio = time.monotonic()
    venda = {"fase": fase, "itens": itens}
    try:
        pedido = _ok(cliente.post("/orders/create-with-item/", json={
            "order_type": "counter", "item": {"product": produtos[0], "quantity": 1}}))
        pedido_id = pedido.get("id") or pedido.get("order", {}).get("id")
        venda["pedido"] = pedido_id
        for n in range(1, itens):
            _ok(cliente.post(f"/orders/{pedido_id}/items/",
                             json={"product": produtos[n % len(produtos)], "quantity": 1}))
        total = _ok(cliente.get(f"/orders/{pedido_id}/"))["total"]
        _ok(cliente.post(f"/orders/{pedido_id}/pay/", json={
            "payment_method": dados["pix"], "amount": str(total),
            "idempotency_key": f"acbr:{uuid.uuid4().hex}"}))
        nota = _ok(cliente.post("/invoices/emit/", json={"order": pedido_id}))
        venda.update(ok=True, total=str(total), nota=nota.get("id"), status=nota.get("status"),
                     tipo=nota.get("emission_type"), chave=nota.get("access_key"),
                     numero=nota.get("number"), segundos=round(time.monotonic() - inicio, 2))
    except Exception as erro:  # noqa: BLE001 — o relatório conta a falha, não a esconde
        venda.update(ok=False, erro=str(erro)[:400])
    return venda


def rodada(dados, quantas, fase):
    clientes = [entrar(dados["caixas"][n]) for n in range(CAIXAS)]
    with ThreadPoolExecutor(CAIXAS) as pool:
        tarefas = [pool.submit(vender, clientes[n % CAIXAS], dados, 1 + n % 3, fase)
                   for n in range(quantas)]
        return [t.result() for t in tarefas]


def main():
    with open(sys.argv[1], encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    vendas = []
    sefaz("online")
    vendas += rodada(dados, 100, "normal")
    vendas.append(vender(entrar(dados["caixas"][0]), dados, 200, "normal-200-itens"))
    sefaz("fora")
    vendas += rodada(dados, 100, "contingencia")
    vendas.append(vender(entrar(dados["caixas"][0]), dados, 200, "contingencia-200-itens"))
    with open(sys.argv[2], "w", encoding="utf-8") as arquivo:
        json.dump(vendas, arquivo, indent=1, ensure_ascii=False)
    for fase in dict.fromkeys(v["fase"] for v in vendas):
        grupo = [v for v in vendas if v["fase"] == fase]
        estados = {}
        for v in grupo:
            chave = f"{v.get('status')}/{v.get('tipo')}" if v["ok"] else "FALHOU"
            estados[chave] = estados.get(chave, 0) + 1
        print(fase, len(grupo), estados)
    for v in [v for v in vendas if not v["ok"]][:5]:
        print("  falha:", v["erro"])


if __name__ == "__main__":
    main()
