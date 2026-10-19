"""A última tag em que ESTE componente foi CONSTRUÍDO de verdade.

Uso (nos workflows, da raiz do repositório):

    python3 scripts/ultima_tag_construida.py frontend.yml "Build e push"

Imprime a tag (vazio = nenhuma: construa). Os workflows comparam os arquivos
do componente com ela para decidir entre construir e re-etiquetar.

Por que não "a tag anterior pelo nome", como era: a tag anterior pode não ter
construído nada. Na v3.0.117 backend e frontend pararam na catraca e não
publicaram; a v3.0.118 se comparou com ela, viu frontend/ igual e só
re-etiquetou a imagem da v3.0.116 — e a v3.0.119 se comparou com a v3.0.118,
que também só tinha re-etiquetado. O relatório de comandas e a ordenação das
tabelas ficaram de fora da produção com três tags dizendo "sucesso".

Re-etiquetar copia a imagem de uma tag ANTERIOR; o que ela contém é o código
da última tag que rodou o passo de build. É com essa que a comparação vale.

Sem a API do Actions (rede, permissão, limite de requisições), devolve VAZIO:
o workflow constrói. Voltar ao critério antigo — a anterior pelo nome — foi a
primeira ideia e reproduzia o próprio defeito (o frontend seria re-etiquetado
de novo). Construir a mais custa minutos de CI; deixar de construir deixa uma
correção fora da produção sem ninguém ver.
"""
import json
import os
import subprocess
import sys
import urllib.request

#: Quantas tags para trás procurar antes de desistir e mandar construir.
LIMITE = 30


def _api(url):
    cabecalhos = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=cabecalhos), timeout=30) as resposta:
        return json.load(resposta)


def _tags_anteriores():
    atual = os.environ.get("GITHUB_REF_NAME", "")
    saida = subprocess.check_output(["git", "tag", "--list", "v*.*.*", "--sort=-v:refname"], text=True)
    return [tag for tag in saida.split() if tag != atual][:LIMITE]


def construiu(workflow, passo, tag, repositorio):
    """Alguma execução deste workflow, nesta tag, rodou `passo` com sucesso?"""
    base = f"https://api.github.com/repos/{repositorio}/actions/workflows/{workflow}/runs"
    for execucao in _api(f"{base}?branch={tag}&event=push&per_page=10")["workflow_runs"]:
        for job in _api(f"{execucao['jobs_url']}?per_page=100")["jobs"]:
            if any(p["name"] == passo and p.get("conclusion") == "success" for p in job.get("steps") or []):
                return True
    return False


def ultima_tag_construida(workflow, passo):
    tags = _tags_anteriores()
    if not tags:
        return ""
    try:
        for tag in tags:
            if construiu(workflow, passo, tag, os.environ["GITHUB_REPOSITORY"]):
                return tag
    except Exception as erro:  # noqa: BLE001 — sem a API, constrói (lado seguro)
        print(f"::warning::Sem a API do Actions ({erro}): sem base confiável para "
              "comparar, o componente será construído.", file=sys.stderr)
        return ""
    return ""


if __name__ == "__main__":
    print(ultima_tag_construida(sys.argv[1], sys.argv[2]))
