"""Renderizacao do relatorio em Markdown.

Separado de `report.py` porque sao dois trabalhos: la se AGREGA (numeros,
percentis, vereditos); aqui se ESCREVE para alguem ler em dois minutos.
"""
import json

from . import result as verdicts

TITULO = "Relatorio de carga StarChef"


def _celula(valor):
    """Resposta de erro tem barra vertical e quebra de linha; sem isto a tabela desmonta."""
    texto = str(valor).replace("|", r"\|")
    return " ".join(texto.split())


def _tabela(linhas, colunas):
    cabecalho = "| " + " | ".join(colunas) + " |"
    separador = "| " + " | ".join("---" for _ in colunas) + " |"
    corpo = ["| " + " | ".join(_celula(linha.get(coluna, "")) for coluna in colunas) + " |" for linha in linhas]
    return chr(10).join([cabecalho, separador, *corpo])


def _pista_de_causa(dados):
    """500 em payload VALIDO, em rota que funciona sozinha, costuma ser o banco.

    Vale dizer isso no relatorio: SQLite serializa escrita e devolve
    "database is locked" sob concorrencia — e um teto do ambiente, nao um bug
    de codigo, e confundir os dois faz perder tempo procurando no lugar errado.
    """
    quebras_validas = sum(
        1 for d in dados["defeitos"]
        if d["veredito"] == verdicts.SERVER_ERROR and d["caso"] in ("valido", "desleixado", "patch_valido")
    )
    if quebras_validas >= 3:
        return (
            "Parte dos 5xx caiu sobre payload valido. Em SQLite isso e quase sempre contencao de "
            "escrita (`database is locked`): repita o mesmo perfil contra Postgres antes de tratar "
            "como defeito de codigo. Confira o log do servidor para separar os dois."
        )
    return ""


def _veredito_geral(dados):
    totais = dados["totais"]
    quebras = totais["por_veredito"].get(verdicts.SERVER_ERROR, 0) + totais["por_veredito"].get(
        verdicts.TRANSPORT_ERROR, 0
    )
    lixo = totais["por_veredito"].get(verdicts.GARBAGE_ACCEPTED, 0)
    checagens = [c for c in dados["verificacoes"] if not c["ok"]]
    if quebras or checagens:
        return "REPROVADO", f"{quebras} respostas quebradas e {len(checagens)} verificacoes de coerencia falharam"
    if lixo:
        return "ATENCAO", f"{lixo} payloads invalidos foram ACEITOS pela API"
    return "APROVADO", "nenhum 5xx, nenhuma queda de conexao e nenhuma incoerencia detectada"


def to_markdown(dados):
    situacao, motivo = _veredito_geral(dados)
    totais = dados["totais"]
    linhas = [
        f"# {TITULO}",
        "",
        f"**Situacao: {situacao}** — {motivo}.",
        "",
        f"- Gerado em: {dados['gerado_em']}",
        f"- Duracao total: {dados['duracao_total_s']} s",
        f"- Suites: {', '.join(dados['suites'])}",
        f"- Requisicoes: **{totais['requisicoes']}** (media {totais['rps_medio']}/s, pico {totais['rps_pico']}/s)",
        f"- Latencia: p50 {totais['p50_ms']} ms | p95 {totais['p95_ms']} ms | p99 {totais['p99_ms']} ms",
        "",
        "## Configuracao",
        "",
        "```json",
        json.dumps(dados["configuracao"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Vereditos",
        "",
        _tabela(
            [
                {"veredito": verdicts.VERDICT_LABELS.get(v, v), "chave": v, "quantidade": q}
                for v, q in sorted(totais["por_veredito"].items(), key=lambda item: -item[1])
            ],
            ["veredito", "chave", "quantidade"],
        ),
        "",
        "## Por grupo",
        "",
        _tabela(
            [
                {
                    "suite": g["suite"], "grupo": g["grupo"], "reqs": g["requisicoes"], "rps": g["rps"],
                    "p50": g["p50_ms"], "p99": g["p99_ms"], "max": g["max_ms"],
                    "5xx": g["vereditos"].get(verdicts.SERVER_ERROR, 0),
                    "sem_resposta": g["vereditos"].get(verdicts.TRANSPORT_ERROR, 0),
                    "lixo_aceito": g["vereditos"].get(verdicts.GARBAGE_ACCEPTED, 0),
                    "429": g["vereditos"].get(verdicts.THROTTLED, 0),
                    "503": g["vereditos"].get(verdicts.OVERLOADED, 0),
                }
                for g in sorted(dados["grupos"], key=lambda item: -item["requisicoes"])
            ],
            ["suite", "grupo", "reqs", "rps", "p50", "p99", "max", "5xx", "sem_resposta", "lixo_aceito", "429", "503"],
        ),
        "",
        "## Verificacoes de coerencia",
        "",
    ]
    pista = _pista_de_causa(dados)
    if pista:
        linhas.insert(4, f"> **Leia antes de abrir chamado:** {pista}")
        linhas.insert(5, "")
    if dados["verificacoes"]:
        linhas.append(
            _tabela(
                [
                    {"suite": c["suite"], "verificacao": c["nome"],
                     "resultado": "OK" if c["ok"] else "FALHOU", "detalhe": c["detalhe"][:160]}
                    for c in dados["verificacoes"]
                ],
                ["suite", "verificacao", "resultado", "detalhe"],
            )
        )
    else:
        linhas.append("_Nenhuma verificacao registrada._")

    linhas += ["", "## Defeitos encontrados", ""]
    if dados["defeitos"]:
        total_defeitos = sum(
            dados["totais"]["por_veredito"].get(v, 0) for v in verdicts.DEFECTS
        )
        if total_defeitos > len(dados["defeitos"]):
            linhas += [
                f"_{total_defeitos} defeitos no total; abaixo uma amostra de {len(dados['defeitos'])} "
                "(no maximo 12 por grupo). A contagem completa esta na tabela por grupo._",
                "",
            ]
        for indice, defeito in enumerate(dados["defeitos"][:80], start=1):
            linhas += [
                f"### {indice}. [{defeito['veredito']}] {defeito['grupo']} — caso `{defeito['caso']}`",
                "",
                f"- HTTP: `{defeito['http']}` {('erro: ' + defeito['erro']) if defeito['erro'] else ''}",
                f"- Requisicao: `{defeito['repro']}`",
                f"- Resposta: `{defeito['resposta']}`",
                "",
            ]
    else:
        linhas.append("_Nenhum defeito: nenhum 5xx, nenhuma conexao derrubada e nenhum payload invalido aceito._")

    suspeitas = dados.get("suspeitas") or []
    if suspeitas:
        linhas += [
            "", "## Suspeitas (payload que deveria valer foi recusado)", "",
            "Nao sao defeitos automaticamente: pode ser regra de negocio. Leia a mensagem",
            "do servidor — se ela nao explica o motivo, a recusa e o problema.", "",
            _tabela(
                [
                    {"grupo": s["grupo"], "caso": s["caso"], "http": s["http"], "resposta": s["resposta"][:110]}
                    for s in suspeitas[:40]
                ],
                ["grupo", "caso", "http", "resposta"],
            ),
        ]

    if dados["observacoes"]:
        linhas += ["", "## Observacoes da execucao", ""]
        linhas += [f"- **{o['suite']}**: {o['texto']}" for o in dados["observacoes"]]
    return "\n".join(linhas) + "\n"
