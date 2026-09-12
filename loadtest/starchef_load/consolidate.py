"""Junta varias execucoes num plano de correcao unico.

Cada execucao responde "o que quebrou nesta frente". Este modulo responde a
pergunta que vem depois: **o que precisa ser corrigido, em que ordem, e onde**.
"""
import collections
import json
import os

from . import result as verdicts
from . import serverlog
from .report_markdown import _tabela

SEVERIDADE = {
    verdicts.SERVER_ERROR: (1, "ALTA"),
    verdicts.TRANSPORT_ERROR: (1, "ALTA"),
    verdicts.GARBAGE_ACCEPTED: (2, "MEDIA"),
}


def adaptar_pdv(dados):
    """Traduz o relatorio do PDV Flutter para o formato desta consolidacao.

    Sao duas suites medindo coisas diferentes — uma bate na API pela rede, a
    outra roda o codigo Dart do terminal. O plano de correcao, porem, e um so:
    quem le quer a lista de defeitos do sistema, nao dois relatorios para
    cruzar na mao.
    """
    totais = dados.get("totais") or {}
    return {
        "_arquivo": dados.get("_arquivo", ""),
        "suites": ["pdv-flutter"],
        "configuracao": {"perfil": (dados.get("configuracao") or {}).get("perfil", "?")},
        "totais": {
            "requisicoes": totais.get("operacoes", 0),
            "rps_medio": 0,
            "rps_pico": 0,
            "p50_ms": 0,
            "p99_ms": 0,
            "por_veredito": {
                verdicts.OK: totais.get("ok", 0),
                verdicts.REJECTED_OK: totais.get("recusa_correta", 0),
                verdicts.GARBAGE_ACCEPTED: totais.get("lixo_aceito", 0),
                verdicts.SERVER_ERROR: totais.get("erro_inesperado", 0),
                verdicts.TRANSPORT_ERROR: totais.get("travou", 0),
            },
        },
        "grupos": [],
        "verificacoes": [
            {
                "suite": "pdv-flutter",
                "nome": item.get("nome", ""),
                "ok": item.get("ok", False),
                "detalhe": f"{item.get('detalhe', '')}",
            }
            for item in dados.get("verificacoes") or []
        ],
        "observacoes": [
            {"suite": "pdv-flutter", "texto": texto}
            for texto in dados.get("observacoes") or []
        ],
        "suspeitas": [],
        "defeitos": [
            {
                "suite": "pdv-flutter",
                "grupo": item.get("operacao", ""),
                "caso": item.get("caso", ""),
                "veredito": verdicts.GARBAGE_ACCEPTED
                if item.get("veredito") == "lixo_aceito"
                else verdicts.SERVER_ERROR,
                "http": 0,
                "erro": item.get("detalhe", ""),
                "resposta": item.get("detalhe", "")[:300],
                "repro": f"{item.get('operacao', '')} ({item.get('ms', '?')} ms)",
            }
            for item in dados.get("problemas") or []
        ],
        "operacoes_lentas": [
            item for item in dados.get("operacoes") or [] if item.get("estourou_orcamento")
        ],
    }


def carregar(caminhos):
    execucoes = []
    for caminho in caminhos:
        try:
            with open(caminho, encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
        except (OSError, ValueError):
            continue
        dados["_arquivo"] = os.path.basename(caminho)
        # O relatorio do PDV tem "operacoes" no lugar de "grupos": e o sinal de
        # que ele veio da suite Dart e precisa ser adaptado.
        if "operacoes" in dados and "grupos" not in dados:
            dados = adaptar_pdv(dados)
        execucoes.append(dados)
    return execucoes


def resumo_execucoes(execucoes):
    linhas = []
    for dados in execucoes:
        totais = dados["totais"]
        linhas.append({
            "execucao": ", ".join(dados["suites"]) or "?",
            "perfil": dados["configuracao"]["perfil"],
            "reqs": totais["requisicoes"],
            "rps_medio": totais["rps_medio"],
            "rps_pico": totais["rps_pico"],
            "p50": totais["p50_ms"],
            "p99": totais["p99_ms"],
            "5xx": totais["por_veredito"].get(verdicts.SERVER_ERROR, 0),
            "lixo_aceito": totais["por_veredito"].get(verdicts.GARBAGE_ACCEPTED, 0),
            "sem_resposta": totais["por_veredito"].get(verdicts.TRANSPORT_ERROR, 0),
            "arquivo": dados["_arquivo"],
        })
    return linhas


def lixo_aceito(execucoes):
    """Payload invalido que a API aceitou — agrupado por rota + tipo de erro."""
    achados = collections.defaultdict(lambda: {"vezes": 0, "exemplo": ""})
    for dados in execucoes:
        for defeito in dados["defeitos"]:
            if defeito["veredito"] != verdicts.GARBAGE_ACCEPTED:
                continue
            chave = (defeito["grupo"], defeito["caso"])
            achados[chave]["vezes"] += 1
            achados[chave]["exemplo"] = achados[chave]["exemplo"] or defeito["repro"]
    return sorted(achados.items(), key=lambda item: -item[1]["vezes"])


def verificacoes_reprovadas(execucoes):
    reprovadas = []
    for dados in execucoes:
        for checagem in dados["verificacoes"]:
            if not checagem["ok"]:
                reprovadas.append(checagem)
    return reprovadas


def suspeitas_agrupadas(execucoes, limite=15):
    contador = collections.Counter()
    exemplo = {}
    for dados in execucoes:
        for suspeita in dados.get("suspeitas") or []:
            chave = (suspeita["grupo"], suspeita["caso"])
            contador[chave] += 1
            exemplo.setdefault(chave, suspeita["resposta"])
    return [(chave, vezes, exemplo[chave]) for chave, vezes in contador.most_common(limite)]


#: Cada verificacao reprovada tem uma acao diferente; um texto generico so
#: adiaria a leitura do detalhe.
ACOES_DE_CHECAGEM = (
    ("duplicado", "ALTA",
     "e a promessa central do offline: conferir a idempotencia do replay antes de liberar. "
     "Se o detalhe diz '0 conferidos', nenhum recebimento chegou — corrija os 500 primeiro"),
    ("healthcheck", "ALTA",
     "o servidor parou de responder sob a carga: e o teto do processo (Daphne dev / workers), "
     "nao um bug de rota. Meça de novo com gunicorn + Postgres"),
    ("presa", "MEDIA",
     "operacao que nao escoou. Veja quantas sao 'orfas de dependencia': elas dependem de uma "
     "criacao recusada, entao a causa esta no erro anterior, nao na fila"),
    ("escoaram", "MEDIA",
     "mesma leitura do item acima: fila do aparelho parada atras de uma operacao recusada"),
    ("index", "MEDIA", "o servidor de estatico caiu na enxurrada; conferir limites do processo"),
)


def acao_para(nome):
    for marca, gravidade, texto in ACOES_DE_CHECAGEM:
        if marca in nome:
            return gravidade, texto
    return "MEDIA", "investigar antes de liberar"


def plano(falhas, aceitos, reprovadas):
    """Itens acionaveis, do mais grave para o menos."""
    itens = []
    for falha in falhas:
        causa, correcao = serverlog.receita(falha.excecao)
        gravidade = "MEDIA" if "OperationalError" in falha.excecao else "ALTA"
        itens.append({
            "gravidade": gravidade,
            "onde": falha.local,
            "sintoma": f"{falha.ocorrencias}x HTTP 500 — {falha.excecao}: {falha.mensagem[:60]}",
            "causa": causa,
            "correcao": correcao,
        })
    for (grupo, caso), info in aceitos:
        itens.append({
            "gravidade": "MEDIA",
            "onde": grupo,
            "sintoma": f"{info['vezes']}x payload invalido ACEITO (caso `{caso}`)",
            "causa": "falta validacao para este campo/valor",
            "correcao": "recusar com 400 no serializer ou no service; hoje o dado entra no banco",
        })
    for checagem in reprovadas:
        gravidade, texto = acao_para(checagem["nome"])
        itens.append({
            "gravidade": gravidade,
            "onde": f"suite {checagem['suite']}",
            "sintoma": f"verificacao reprovou: {checagem['nome']} — {checagem['detalhe'][:90]}",
            "causa": checagem["detalhe"][:120],
            "correcao": texto,
        })
    ordem = {"ALTA": 0, "MEDIA": 1, "BAIXA": 2}
    return sorted(itens, key=lambda item: ordem.get(item["gravidade"], 3))


def tabela_plano(itens):
    return _tabela(
        [
            {"#": indice, "gravidade": item["gravidade"], "onde": item["onde"],
             "sintoma": item["sintoma"], "correcao": item["correcao"]}
            for indice, item in enumerate(itens, start=1)
        ],
        ["#", "gravidade", "onde", "sintoma", "correcao"],
    )
