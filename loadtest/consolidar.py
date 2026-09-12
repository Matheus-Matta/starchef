#!/usr/bin/env python
"""Junta as execucoes de carga num relatorio unico de correcoes.

    python loadtest/consolidar.py artifacts/loadtest/carga-*.json --server-log artifacts/loadtest/servidor.log

Sai um Markdown com: resumo de cada execucao, causas raiz dos 500 (cruzando com
o traceback do servidor), payloads invalidos que a API aceitou, verificacoes de
coerencia reprovadas e o plano de correcao ordenado por gravidade.
"""
import argparse
import datetime
import glob
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from starchef_load import consolidate, serverlog  # noqa: E402
from starchef_load.report_markdown import _tabela  # noqa: E402


def montar(execucoes, falhas):
    aceitos = consolidate.lixo_aceito(execucoes)
    reprovadas = consolidate.verificacoes_reprovadas(execucoes)
    itens = consolidate.plano(falhas, aceitos, reprovadas)
    total_reqs = sum(d["totais"]["requisicoes"] for d in execucoes)
    altas = sum(1 for item in itens if item["gravidade"] == "ALTA")

    linhas = [
        "# Plano de correcao — teste de carga StarChef",
        "",
        f"Gerado em {datetime.datetime.now().isoformat(timespec='seconds')} a partir de "
        f"{len(execucoes)} execucoes e {total_reqs} requisicoes.",
        "",
        f"**{len(itens)} itens acionaveis, {altas} de gravidade ALTA.**",
        "",
        "## 1. Execucoes",
        "",
        "Nas suites `desktop` e `mobile` o mesmo 5xx aparece varias vezes: a fila offline",
        "retenta a operacao pela escada de backoff antes de desistir. Conte causas raiz na",
        "secao 3, nao linhas aqui. `sem_resposta` e conexao derrubada — saturacao do processo,",
        "nao erro de rota.",
        "",
        _tabela(
            consolidate.resumo_execucoes(execucoes),
            ["execucao", "perfil", "reqs", "rps_medio", "rps_pico", "p50", "p99",
             "5xx", "lixo_aceito", "sem_resposta"],
        ),
        "",
        "## 2. Plano de correcao",
        "",
        consolidate.tabela_plano(itens) if itens else "_Nada a corrigir._",
        "",
        "## 3. Causas raiz dos 500 (log do servidor)",
        "",
    ]
    if falhas:
        for indice, falha in enumerate(falhas, start=1):
            causa, correcao = serverlog.receita(falha.excecao)
            rotas = ", ".join(f"`{rota}` ({vezes}x)" for rota, vezes in falha.rotas_ordenadas()) or "varias"
            linhas += [
                f"### {indice}. `{falha.excecao}` em {falha.local} — {falha.ocorrencias}x",
                "",
                f"- Mensagem: `{falha.mensagem[:160]}`",
                f"- Rotas mais atingidas: {rotas}",
                f"- Causa: {causa}",
                f"- Correcao: {correcao}",
                "",
            ]
    else:
        linhas.append("_Nenhum 500 no log do servidor durante estas execucoes._")

    total_lixo = sum(
        d["totais"]["por_veredito"].get("lixo_aceito", 0) for d in execucoes
    )
    linhas += ["", "## 4. Payload invalido que a API aceitou", ""]
    if aceitos:
        amostrados = sum(info["vezes"] for _, info in aceitos)
        if total_lixo > amostrados:
            linhas += [
                f"_{total_lixo} ocorrencias no total; a tabela mostra {amostrados} amostradas "
                "(no maximo 12 por grupo)._",
                "",
            ]
        linhas.append(_tabela(
            [
                {"rota/fluxo": grupo, "caso": caso, "vezes": info["vezes"],
                 "exemplo": info["exemplo"][:150]}
                for (grupo, caso), info in aceitos
            ],
            ["rota/fluxo", "caso", "vezes", "exemplo"],
        ))
    else:
        linhas.append("_Nenhum: todo payload invalido foi recusado._")

    linhas += ["", "## 5. Verificacoes de coerencia reprovadas", ""]
    if reprovadas:
        linhas.append(_tabela(
            [{"suite": c["suite"], "verificacao": c["nome"], "detalhe": c["detalhe"][:180]} for c in reprovadas],
            ["suite", "verificacao", "detalhe"],
        ))
    else:
        linhas.append("_Todas passaram._")

    suspeitas = consolidate.suspeitas_agrupadas(execucoes)
    linhas += ["", "## 6. Suspeitas (recusa que talvez nao devesse existir)", ""]
    if suspeitas:
        linhas += [
            "Regra de negocio legitima ou mensagem ruim? Decida lendo a resposta.",
            "",
            _tabela(
                [{"rota/fluxo": chave[0], "caso": chave[1], "vezes": vezes, "resposta": resposta[:130]}
                 for chave, vezes, resposta in suspeitas],
                ["rota/fluxo", "caso", "vezes", "resposta"],
            ),
        ]
    else:
        linhas.append("_Nenhuma._")
    return "\n".join(linhas) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Consolida execucoes de carga num plano de correcao.")
    parser.add_argument("reports", nargs="+", help="arquivos JSON de relatorio (aceita curinga)")
    parser.add_argument("--server-log", dest="server_log", default="", help="log JSON do Django durante as execucoes")
    parser.add_argument("--out", default="artifacts/loadtest/PLANO-DE-CORRECAO.md")
    args = parser.parse_args(argv)

    caminhos = []
    for padrao in args.reports:
        caminhos.extend(sorted(glob.glob(padrao)) or [padrao])
    execucoes = consolidate.carregar(caminhos)
    if not execucoes:
        print("nenhum relatorio JSON legivel encontrado")
        return 2
    falhas = serverlog.ler(args.server_log) if args.server_log else []

    texto = montar(execucoes, falhas)
    destino = pathlib.Path(args.out)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"\nPlano gravado em {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
