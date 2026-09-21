#!/usr/bin/env python3
"""Catraca do limite de 200 linhas por arquivo.

O `AGENTS.md` pede no máximo 200 linhas por arquivo desde sempre, mas 201 dos
805 arquivos do monorepo já passam disso. Uma trava dura reprovaria todo mundo
no primeiro dia e seria desligada na primeira urgência — que é como um padrão
morre.

Uma **catraca** resolve os dois lados: o que já estava grande fica registrado
numa linha de base e não reprova ninguém; o que nasce grande, ou o que cresce
além do que já era, reprova. O limite só pode andar para baixo.

    python scripts/check_tamanho_de_arquivo.py            # confere
    python scripts/check_tamanho_de_arquivo.py --atualizar  # regrava a base

A base é `scripts/tamanho_de_arquivo.baseline.json`, versionada de propósito:
ela é a lista do que a equipe ainda deve quebrar, e encolher essa lista é
trabalho visível no diff.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# O console do Windows abre em cp1252, e um `→` ou um `✓` no relatório derruba
# o script com `UnicodeEncodeError` — no CI isso vira uma falha que não tem
# nada a ver com o que se está medindo. Reconfigurar a saída é mais honesto do
# que escrever só ASCII e fingir que o problema não existe.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
BASE = Path(__file__).resolve().parent / "tamanho_de_arquivo.baseline.json"

LIMITE = 200

#: Onde procurar, por superfície. A chave é o rótulo que sai no relatório.
SUPERFICIES = {
    "backend": ("backend/apps", (".py",)),
    "frontend": ("frontend/src", (".js", ".vue")),
    "desktop": ("pdv_desktop/lib", (".dart",)),
    "mobile": ("pdv_mobile/lib", (".dart",)),
    "storefront": ("storefront", (".js", ".vue", ".ts")),
}

#: Gerado por ferramenta, não por pessoa: contar linhas aqui não mede nada.
IGNORAR = (
    "/migrations/",
    "/node_modules/",
    "/.nuxt/",
    "/dist/",
    "/build/",
    ".g.dart",
    ".freezed.dart",
)


def _relevante(caminho: Path) -> bool:
    texto = caminho.as_posix()
    return not any(pedaco in texto for pedaco in IGNORAR)


def medir() -> dict[str, int]:
    """Quantas linhas tem cada arquivo que passa do limite, hoje."""
    grandes: dict[str, int] = {}
    for pasta, extensoes in SUPERFICIES.values():
        base = RAIZ / pasta
        if not base.exists():
            continue
        for extensao in extensoes:
            for caminho in base.rglob(f"*{extensao}"):
                if not _relevante(caminho):
                    continue
                try:
                    linhas = len(caminho.read_text(encoding="utf-8").splitlines())
                except (UnicodeDecodeError, OSError):
                    continue
                if linhas > LIMITE:
                    grandes[caminho.relative_to(RAIZ).as_posix()] = linhas
    return dict(sorted(grandes.items()))


def carregar_base() -> dict[str, int]:
    if not BASE.exists():
        return {}
    return json.loads(BASE.read_text(encoding="utf-8"))["arquivos"]


def gravar_base(grandes: dict[str, int]) -> None:
    conteudo = {
        "_leia_me": (
            "Linha de base da catraca de tamanho de arquivo. Cada entrada é um "
            "arquivo que JÁ passava de 200 linhas quando a regra passou a ser "
            "medida. A lista só pode encolher: quebrar um destes arquivos e "
            "rodar --atualizar é o jeito de baixar a dívida."
        ),
        "limite": LIMITE,
        "arquivos": grandes,
    }
    BASE.write_text(json.dumps(conteudo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def conferir() -> int:
    atual = medir()
    base = carregar_base()

    novos = {nome: linhas for nome, linhas in atual.items() if nome not in base}
    cresceram = {
        nome: (base[nome], linhas)
        for nome, linhas in atual.items()
        if nome in base and linhas > base[nome]
    }
    resolvidos = [nome for nome in base if nome not in atual]

    if resolvidos:
        print(f"✓ {len(resolvidos)} arquivo(s) saíram da dívida:")
        for nome in resolvidos[:10]:
            print(f"    {nome}")
        print("  Rode --atualizar para registrar o ganho.\n")

    if not novos and not cresceram:
        print(f"OK: nenhum arquivo novo passou de {LIMITE} linhas.")
        print(f"    Dívida atual: {len(base)} arquivo(s) na linha de base.")
        return 0

    for nome, linhas in novos.items():
        print(f"NOVO  {nome}: {linhas} linhas (limite {LIMITE})")
    for nome, (antes, agora) in cresceram.items():
        print(f"CRESCEU  {nome}: {antes} → {agora} linhas")

    if novos:
        print(
            "\nARQUIVO NOVO acima do limite não tem exceção: quebre em módulos "
            "com uma responsabilidade cada.\n"
            "A regra é do AGENTS.md — no máximo 200 linhas por arquivo."
        )
    if cresceram:
        print(
            "\nARQUIVO QUE JÁ ERA GRANDE cresceu. Duas saídas, nesta ordem:\n"
            "  1. Quebre o arquivo — é o motivo de a lista existir.\n"
            "  2. Se o que entrou paga o crescimento (um comentário que explica\n"
            "     um porquê difícil, uma correção que precisa de contexto),\n"
            "     rode --atualizar e deixe o crescimento VISÍVEL no diff.\n"
            "\n"
            "A segunda saída não é uma brecha: a linha de base é versionada de\n"
            "propósito, então quem revisa vê o arquivo crescer e pode perguntar\n"
            "por quê. O que não pode é crescer em silêncio."
        )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--atualizar",
        action="store_true",
        help="Regrava a linha de base com o estado atual (use ao baixar a dívida).",
    )
    args = parser.parse_args()

    if args.atualizar:
        grandes = medir()
        gravar_base(grandes)
        print(f"Linha de base regravada: {len(grandes)} arquivo(s) acima de {LIMITE} linhas.")
        return 0
    return conferir()


if __name__ == "__main__":
    sys.exit(main())
