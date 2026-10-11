"""Conferência da emissão: a SEFAZ (simulada) e os dois bancos contam a mesma história.

Uso: `python conferir.py <saida-do-emitir.json>`. Espera a sincronização
assentar e confere:

1. toda nota está autorizada (`issued`), nenhuma em erro ou pendente;
2. a nota de contingência foi autorizada com A MESMA chave do cupom impresso
   (tpEmis=9 na chave) — a retransmissão não pode refazer a nota;
3. nenhum número repetido na série, e uma nota por pedido;
4. nota e item de nota existem nos DOIS bancos com os mesmos valores;
5. nenhum evento de sincronização morto ou em conflito.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dia_a_dia"))
from conferir import esperar_assentar, sql  # noqa: E402

NOTA = ("SELECT id, order_id, status, emission_type, number, series, access_key, "
        "authorization_protocol, total_amount FROM invoices_invoice")
ITEM = "SELECT id, invoice_id, quantity, total_price FROM invoices_invoiceitem"


def main():
    with open(sys.argv[1], encoding="utf-8") as arquivo:
        vendas = json.load(arquivo)
    falhas = []
    assentou, transito = esperar_assentar()
    print("sincronizacao assentou:", assentou, transito)

    notas = {lado: {linha[0]: linha for linha in sql(lado, NOTA)} for lado in ("loja", "nuvem")}
    loja = notas["loja"]
    print("notas por estado (loja):", Counter(f"{n[2]}/{n[3]}" for n in loja.values()))
    falhas += [f"nota {n[0]} terminou {n[2]}" for n in loja.values() if n[2] != "issued"]

    for venda in vendas:
        nota = loja.get(venda.get("nota") or "")
        if not nota:
            falhas.append(f"venda {venda.get('pedido')} sem nota no banco da loja")
        elif venda.get("tipo") == "9" and (nota[6] != venda["chave"] or nota[6][34] != "9"):
            falhas.append(f"contingência {nota[0]}: chave do cupom {venda['chave']} virou {nota[6]}")
    contingencias = sum(1 for v in vendas if v.get("tipo") == "9")
    print(f"contingências com a chave do cupom preservada: {contingencias}")

    repetidos = [k for k, n in Counter((n[5], n[4]) for n in loja.values()).items() if n > 1]
    por_pedido = [k for k, n in Counter(n[1] for n in loja.values()).items() if n > 1]
    falhas += [f"número repetido série/numero {k}" for k in repetidos]
    falhas += [f"pedido {k} com mais de uma nota" for k in por_pedido]
    sem_protocolo = [n[0] for n in loja.values() if n[2] == "issued" and not n[7]]
    falhas += [f"nota {k} autorizada sem protocolo" for k in sem_protocolo]

    for nome, consulta in (("nota", NOTA), ("item de nota", ITEM)):
        lados = {lado: {linha[0]: linha for linha in sql(lado, consulta)} for lado in ("loja", "nuvem")}
        so_loja = set(lados["loja"]) - set(lados["nuvem"])
        so_nuvem = set(lados["nuvem"]) - set(lados["loja"])
        diferentes = [k for k in set(lados["loja"]) & set(lados["nuvem"])
                      if lados["loja"][k] != lados["nuvem"][k]]
        print(f"{nome}: loja={len(lados['loja'])} nuvem={len(lados['nuvem'])} "
              f"só-loja={len(so_loja)} só-nuvem={len(so_nuvem)} diferentes={len(diferentes)}")
        falhas += [f"{nome} {k} só na loja" for k in so_loja]
        falhas += [f"{nome} {k} só na nuvem" for k in so_nuvem]
        falhas += [f"{nome} {k}: loja {lados['loja'][k]} x nuvem {lados['nuvem'][k]}" for k in diferentes]

    for lado in ("loja", "nuvem"):
        mortos = sql(lado, "SELECT status, count(*) FROM synchronization_syncevent "
                           "WHERE status IN ('DEAD','CONFLICT') GROUP BY 1")
        falhas += [f"{lado}: {n} eventos {s}" for s, n in mortos]
        print(f"{lado}: eventos mortos/conflito = {mortos or 'nenhum'}")

    print("\nRESULTADO:", "OK" if not falhas else f"{len(falhas)} FALHAS")
    for falha in falhas[:30]:
        print("  -", falha)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
