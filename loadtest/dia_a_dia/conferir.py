"""A conferência: os dois bancos batem, e nada foi duplicado nem perdido.

Primeiro espera a sincronização assentar (nenhum evento em trânsito nos dois
lados). Depois:

1. **Espelho.** Pedido, item da comanda, item do pedido, recebimento, sessão e
   movimento de caixa, leitura de balança: cada linha criada na simulação
   existe nos DOIS bancos, com os mesmos valores.
2. **Intenção x banco.** Cada lançamento, pesagem e recebimento tem uma marca
   única. Contada no banco: mais de uma = DUPLICADO; zero com o cliente tendo
   recebido sucesso = PERDIDO.
3. **Conta fechada.** Recebido aprovado de cada pedido == total do pedido.
"""
import subprocess
import time
from collections import Counter
from decimal import Decimal

BANCO = {"nuvem": ("starchef-pg-cloud", "starchef_cloud"),
         "loja": ("starchef-pg-store", "starchef_store")}
EM_TRANSITO = ("'PENDING','PROCESSING','SENT','RECEIVED','FAILED'")

ESPELHOS = {
    "pedido": ("orders_order", "id,status,payment_status,total", "opened_at"),
    "item_da_comanda": ("orders_commanditem", "id,command_status,status,quantity,total_price",
                        "launched_at"),
    "item_do_pedido": ("orders_orderitem", "id,order_id,status,quantity,total_price", "launched_at"),
    "recebimento": ("payments_payment", "id,order_id,amount,status", "paid_at"),
    "sessao_de_caixa": ("payments_cashregister", "id,status", "created_at"),
    "movimento_de_caixa": ("payments_cashmovement", "id,amount,status", "created_at"),
    "leitura_da_balanca": ("printers_scalereading", "id,weight_kg,command_item_id", "created_at"),
}


def sql(lado, consulta):
    container, banco = BANCO[lado]
    feito = subprocess.run(["docker", "exec", container, "psql", "-U", "starchef", "-d", banco,
                            "-qtAF", "|", "-c", consulta], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
    if feito.returncode:
        raise RuntimeError(f"{lado}: {feito.stderr.strip()[:300]}")
    return [linha.split("|") for linha in feito.stdout.splitlines() if linha.strip()]


def em_transito():
    return {lado: int(sql(lado, f"SELECT count(*) FROM synchronization_syncevent "
                                f"WHERE status IN ({EM_TRANSITO})")[0][0]) for lado in BANCO}


def esperar_assentar(limite=900):
    fim, zerado_seguido = time.monotonic() + limite, 0
    while time.monotonic() < fim:
        agora = em_transito()
        zerado_seguido = zerado_seguido + 1 if not any(agora.values()) else 0
        if zerado_seguido >= 3:
            return True, agora
        time.sleep(5)
    return False, em_transito()


def espelho(nome, desde):
    tabela, colunas, quando = ESPELHOS[nome]
    linhas = {lado: {r[0]: r[1:] for r in sql(lado, f"SELECT {colunas} FROM {tabela} "
                                                   f"WHERE {quando} >= '{desde}'")} for lado in BANCO}
    nuvem, loja = linhas["nuvem"], linhas["loja"]
    so_nuvem = sorted(set(nuvem) - set(loja))
    so_loja = sorted(set(loja) - set(nuvem))
    diferentes = sorted(i for i in set(nuvem) & set(loja) if nuvem[i] != loja[i])
    exemplos = [f"{i}: nuvem={nuvem[i]} loja={loja[i]}" for i in diferentes[:3]]
    return {"linhas": len(nuvem), "so_na_nuvem": len(so_nuvem), "so_na_loja": len(so_loja),
            "diferentes": len(diferentes), "exemplos": exemplos}


def contar_marcas(lado, desde):
    itens = Counter(r[0] for r in sql(lado, "SELECT customer_note FROM orders_commanditem "
                                            f"WHERE customer_note LIKE 'sim:%' AND launched_at >= '{desde}'"))
    pagos = Counter(r[0] for r in sql(lado, "SELECT metadata->>'sim_intencao' FROM payments_payment "
                                            f"WHERE status='approved' AND paid_at >= '{desde}' "
                                            "AND metadata ? 'sim_intencao'"))
    pesos = Counter((r[0], Decimal(r[1])) for r in sql(
        lado, "SELECT command_id, quantity FROM orders_commanditem WHERE customer_note = '' "
              "AND product_id IN (SELECT product_id FROM printers_scale) "
              f"AND launched_at >= '{desde}'"))
    return itens, pagos, pesos


def intencoes(registro, lado, desde):
    itens, pagos, pesos = contar_marcas(lado, desde)
    achados = []
    for item in registro.itens:
        n = itens.get(item["marca"], 0)
        if n > 1 or (item.get("ok") and n == 0):
            achados.append(f"item {item['marca']} x{n} (cliente: {'ok' if item.get('ok') else 'falhou'})")
    for pesagem in registro.pesagens:
        n = pesos.get((pesagem["comanda"], Decimal(pesagem["peso"])), 0)
        if n > 1 or (pesagem.get("ok") and n == 0):
            achados.append(f"pesagem {pesagem['peso']} kg x{n}")
    for conta in registro.pedidos:
        for pagamento in conta["pagamentos"]:
            n = pagos.get(pagamento["marca"], 0)
            if n > 1 or (pagamento.get("ok") and n == 0):
                achados.append(f"recebimento {pagamento['marca']} x{n} pedido {conta.get('pedido')}")
    return achados


def contas_fechadas(lado, desde):
    consulta = ("SELECT o.id, o.total, o.status, COALESCE(sum(p.amount) FILTER "
                "(WHERE p.status='approved'),0) FROM orders_order o LEFT JOIN payments_payment p "
                f"ON p.order_id=o.id WHERE o.opened_at >= '{desde}' GROUP BY o.id")
    achados = [f"pedido {i} total {t} recebido {r} ({s})" for i, t, s, r in sql(lado, consulta)
               if Decimal(r) > 0 and Decimal(r) != Decimal(t)]
    # Pago e sem item: o consumo foi cobrado em OUTRO pedido também (a mesma
    # comanda fechada nos dois lados) — dinheiro em dobro.
    vazios = sql(lado, "SELECT o.id, o.total FROM orders_order o WHERE o.status='paid' "
                       f"AND o.total > 0 AND o.opened_at >= '{desde}' AND NOT EXISTS (SELECT 1 "
                       "FROM orders_orderitem i WHERE i.order_id=o.id)")
    return achados + [f"pedido {i} pago ({t}) SEM ITENS — cobrança em dobro?" for i, t in vazios]
