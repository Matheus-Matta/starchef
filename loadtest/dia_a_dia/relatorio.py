"""O veredito do dia simulado, em texto e em JSON.

Aprovado só quando: a sincronização assentou, os dois bancos são espelho, nada
foi duplicado nem perdido, toda conta recebida fecha com o total, nenhum evento
morreu e o servidor não respondeu errado. Qualquer item fora disso reprova.
"""
import json
from collections import Counter
from datetime import datetime

import conferir


def _resumo(lista, chave="ok"):
    return {"total": len(lista), "ok": sum(1 for x in lista if x.get(chave)),
            "falhou": sum(1 for x in lista if not x.get(chave))}


def escrever(registro, terminais, desde, assentou, transito, pasta):
    espelhos = {nome: conferir.espelho(nome, desde) for nome in conferir.ESPELHOS}
    intencao = {lado: conferir.intencoes(registro, lado, desde) for lado in conferir.BANCO}
    contas = {lado: conferir.contas_fechadas(lado, desde) for lado in conferir.BANCO}
    mortos = {lado: int(conferir.sql(lado, "SELECT count(*) FROM synchronization_syncevent "
                                           "WHERE status='DEAD'")[0][0]) for lado in conferir.BANCO}
    conflitos = {lado: int(conferir.sql(lado, "SELECT count(*) FROM synchronization_syncconflict "
                                              "WHERE status='OPEN'")[0][0]) for lado in conferir.BANCO}
    pagamentos = [p for c in registro.pedidos for p in c["pagamentos"]]
    origens = Counter()
    for terminal in terminais.values():
        origens.update(terminal.origens)

    reprovas = []
    if not assentou:
        reprovas.append(f"a sincronização não assentou: {transito}")
    for nome, e in espelhos.items():
        if e["so_na_nuvem"] or e["so_na_loja"] or e["diferentes"]:
            reprovas.append(f"{nome}: só na nuvem {e['so_na_nuvem']}, só na loja {e['so_na_loja']}, "
                            f"diferentes {e['diferentes']} {e['exemplos']}")
    for lado in conferir.BANCO:
        reprovas += [f"[{lado}] {a}" for a in intencao[lado]]
        reprovas += [f"[{lado}] {a}" for a in contas[lado]]
        if mortos[lado]:
            reprovas.append(f"[{lado}] {mortos[lado]} evento(s) DEAD")
        if conflitos[lado]:
            reprovas.append(f"[{lado}] {conflitos[lado]} conflito(s) abertos")
    reprovas += registro.anomalias

    resultado = {
        "quando": datetime.now().isoformat(timespec="seconds"),
        "aprovado": not reprovas,
        "lancamentos": _resumo(registro.itens), "pesagens": _resumo(registro.pesagens),
        "contas": {"total": len(registro.pedidos),
                   "fechadas": sum(1 for c in registro.pedidos if c.get("status") or c.get("pago")),
                   "com_erro": sum(1 for c in registro.pedidos if c.get("erro"))},
        "recebimentos": _resumo(pagamentos),
        "atendido_por": dict(origens), "quedas": registro.eventos,
        "espelhos": espelhos, "mortos": mortos, "conflitos": conflitos, "reprovas": reprovas,
        "erros_de_cliente": [x.get("erro") for x in registro.itens + registro.pesagens + pagamentos
                             if x.get("erro")][:40],
    }
    pasta.mkdir(exist_ok=True)
    (pasta / "ultimo.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    print(json.dumps({k: v for k, v in resultado.items() if k != "espelhos"}, indent=2,
                     ensure_ascii=False))
    print("\nespelho por tabela:")
    for nome, e in espelhos.items():
        print(f"  {nome:20} {e['linhas']:5} linhas  só nuvem {e['so_na_nuvem']}  "
              f"só loja {e['so_na_loja']}  diferentes {e['diferentes']}")
    print("\nVEREDITO:", "APROVADO" if resultado["aprovado"] else f"REPROVADO ({len(reprovas)} achados)")
    return resultado
