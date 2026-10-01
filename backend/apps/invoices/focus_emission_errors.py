"""Leitura das falhas HTTP devolvidas pela Focus durante a emissao."""


def detail_from_focus(data):
    """Prefere a mensagem humana e evita mostrar o dicionario inteiro."""

    if isinstance(data, dict):
        return data.get("mensagem") or data.get("message") or data.get("detail") or str(data)
    return str(data or "")


def is_company_configuration_error(code, data):
    """Reconhece o 422 que so se resolve no cadastro da empresa."""

    if code != 422 or not isinstance(data, dict) or data.get("codigo") != "erro_validacao":
        return False
    detail = detail_from_focus(data).casefold()
    return "csc" in detail or "id token" in detail
