"""Para qual view uma importação grava — e se ela pode.

A importação passa pela MESMA view da tela: mesma validação, mesmas
permissões, mesmo restaurante. Aqui só se acha qual é, a partir da rota.
"""
from django.urls import Resolver404, resolve

PREFIXO = "/api/v1"


class AlvoInvalido(ValueError):
    pass


def resolver_alvo(endpoint):
    """A classe do viewset da listagem `endpoint` (ex.: "/menu/products/")."""
    rota = str(endpoint or "").strip()
    if not rota.startswith("/") or not rota.endswith("/") or ".." in rota:
        raise AlvoInvalido("Rota de importação inválida.")
    try:
        encontrado = resolve(PREFIXO + rota)
    except Resolver404:
        raise AlvoInvalido("Esta tela não aceita importação.") from None
    classe = getattr(encontrado.func, "cls", None)
    acoes = getattr(encontrado.func, "actions", None) or {}
    if classe is None or acoes.get("post") != "create":
        raise AlvoInvalido("Esta tela não aceita importação.")
    return classe


def campo_chave_valido(classe, chave):
    """A chave tem de ser um campo de verdade do model (vira filtro)."""
    if not chave:
        return ""
    modelo = classe.queryset.model if getattr(classe, "queryset", None) is not None else None
    nomes = {campo.name for campo in modelo._meta.concrete_fields} if modelo else set()
    if chave not in nomes:
        raise AlvoInvalido(f"Campo-chave desconhecido: {chave}.")
    return chave
