"""Relatorio final: o que aconteceu, em Markdown e em JSON.

O JSON existe para comparar duas execucoes (antes/depois de uma correcao). O
Markdown existe para alguem ler em dois minutos e saber se pode subir.
"""
import datetime
import json
import os

from . import result as verdicts
from .metrics import percentile
from .report_markdown import to_markdown  # noqa: F401 — reexportado: quem agrega tambem escreve


def build(recorder, config, suites_executadas, elapsed):
    grupos = []
    for chave, stats in sorted(recorder.groups.items()):
        resumo = stats.summary()
        resumo["suite"] = chave.split("::", 1)[0]
        grupos.append(resumo)

    totais = {
        "requisicoes": sum(g["requisicoes"] for g in grupos),
        "defeitos": 0,
        "por_veredito": {},
    }
    for grupo in grupos:
        for veredito, quantidade in grupo["vereditos"].items():
            totais["por_veredito"][veredito] = totais["por_veredito"].get(veredito, 0) + quantidade
    totais["defeitos"] = sum(totais["por_veredito"].get(v, 0) for v in verdicts.DEFECTS)
    latencias = sorted(l for stats in recorder.groups.values() for l in stats.latencies)
    totais["p50_ms"] = round(percentile(latencias, 0.50), 1)
    totais["p95_ms"] = round(percentile(latencias, 0.95), 1)
    totais["p99_ms"] = round(percentile(latencias, 0.99), 1)
    totais["rps_medio"] = round(totais["requisicoes"] / elapsed, 1) if elapsed else 0
    totais["rps_pico"] = recorder.peak_rps()

    return {
        "gerado_em": datetime.datetime.now().isoformat(timespec="seconds"),
        "duracao_total_s": round(elapsed, 1),
        "configuracao": config.describe(),
        "suites": suites_executadas,
        "totais": totais,
        "grupos": grupos,
        "verificacoes": recorder.checks,
        "observacoes": recorder.notes,
        "suspeitas": [
            {
                "suite": d.suite, "grupo": d.group, "caso": d.case, "http": d.status,
                "resposta": d.detail[:220], "repro": d.repro(),
            }
            for d in recorder.suspects()
        ],
        "defeitos": [
            {
                "suite": d.suite, "grupo": d.group, "caso": d.case, "veredito": d.verdict,
                "http": d.status, "erro": d.error, "resposta": d.detail[:300], "repro": d.repro(),
            }
            for d in recorder.defects()
        ],
    }


def write(dados, diretorio, label=""):
    os.makedirs(diretorio, exist_ok=True)
    carimbo = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    sufixo = f"-{label}" if label else ""
    base = os.path.join(diretorio, f"carga-{carimbo}{sufixo}")
    with open(f"{base}.json", "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, indent=2, ensure_ascii=False)
    with open(f"{base}.md", "w", encoding="utf-8") as arquivo:
        arquivo.write(to_markdown(dados))
    return f"{base}.md", f"{base}.json"
