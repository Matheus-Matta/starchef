"""O cliente HTTP do comunicador ACBrLib — e a tradução de cada falha.

A família da falha decide o que a nota faz depois (`contingency.py`), então a
tradução é a parte que importa deste arquivo:

* não alcançou o comunicador, ou ele não alcançou a SEFAZ antes de enviar →
  `FiscalUnavailable`: contingência (se permitida) ou retentativa;
* tempo esgotado → `FiscalAmbiguous`: a SEFAZ pode ter autorizado. Só consulta;
  reenviar ou entrar em contingência aqui é o caminho da nota em dobro;
* documento inválido (schema, assinatura) → `FiscalRejection`;
* certificado, CSC, token ou lib ausente → `FiscalConfigurationError`.
"""
import requests
from django.conf import settings

from apps.invoices.providers_erros import (
    FiscalAmbiguous,
    FiscalConfigurationError,
    FiscalRejection,
    FiscalUnavailable,
)

#: `erro` que o comunicador devolve, e a família de cada um.
_FAMILIAS = {
    "sem_comunicacao": FiscalUnavailable,
    "incerto": FiscalAmbiguous,
    "documento_invalido": FiscalRejection,
    "configuracao": FiscalConfigurationError,
}


def configurado():
    return bool((getattr(settings, "ACBRLIB_URL", "") or "").strip())


def chamar(rota, corpo=None, *, metodo="POST"):
    """Chama o comunicador. Devolve o JSON; falha vira a família certa."""
    base = (getattr(settings, "ACBRLIB_URL", "") or "").rstrip("/")
    if not base:
        raise FiscalConfigurationError(
            "ACBrLib: ACBRLIB_URL não configurada nesta instalação (.env do backend)."
        )
    cabecalhos = {"Accept": "application/json"}
    token = getattr(settings, "ACBRLIB_TOKEN", "") or ""
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    try:
        resposta = requests.request(
            metodo, f"{base}{rota}", json=corpo, headers=cabecalhos,
            timeout=int(getattr(settings, "ACBRLIB_TIMEOUT", 40)),
        )
    except requests.Timeout as erro:
        raise FiscalAmbiguous(
            "ACBrLib: o comunicador não respondeu a tempo. A nota pode ter sido "
            "autorizada — ela será consultada antes de qualquer reenvio."
        ) from erro
    except requests.RequestException as erro:
        raise FiscalUnavailable(f"ACBrLib: comunicador fora do ar ({erro}).") from erro
    return _ler(resposta)


def _ler(resposta):
    try:
        dados = resposta.json()
    except ValueError:
        dados = {}
    if resposta.status_code in (401, 403):
        raise FiscalConfigurationError(
            "ACBrLib: o comunicador recusou o token (ACBRLIB_TOKEN diferente nos dois lados)."
        )
    if resposta.status_code in (502, 503, 504):
        raise FiscalUnavailable(f"ACBrLib: comunicador indisponível (HTTP {resposta.status_code}).")
    if resposta.status_code >= 400 or dados.get("erro"):
        familia = _FAMILIAS.get(dados.get("erro"), FiscalAmbiguous)
        mensagem = dados.get("mensagem") or f"HTTP {resposta.status_code}"
        raise familia(f"ACBrLib: {mensagem}")
    return dados
