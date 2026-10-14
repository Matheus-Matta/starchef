"""O cliente HTTP do comunicador ACBrLib — e a tradução de cada falha.

A família da falha decide o que a nota faz depois (`contingency.py`), então a
tradução é a parte que importa deste arquivo:

* não alcançou o comunicador, ou ele não alcançou a SEFAZ antes de enviar →
  `FiscalUnavailable`: contingência (se permitida) ou retentativa;
* tempo esgotado → `FiscalAmbiguous`: a SEFAZ pode ter autorizado. Só consulta;
  reenviar ou entrar em contingência aqui é o caminho da nota em dobro;
* documento inválido (schema, assinatura) → `FiscalRejection`;
* certificado, CSC, token ou lib ausente → `FiscalConfigurationError`.

O `motivo` que o comunicador manda (`acbrlib_ausente`, `senha_invalida`,
`sefaz_sem_comunicacao`...) fica na exceção, e a frase ganha a providência.
A senha e o certificado enviados SAEM da frase antes de ela ser gravada na
nota ou logada: a lib às vezes ecoa o que recebeu.
"""
import requests
from django.conf import settings

from apps.invoices.providers_erros import (
    FiscalAmbiguous,
    FiscalConfigurationError,
    FiscalRejection,
    FiscalUnavailable,
)

#: A providência de cada `motivo`, à frente da frase da lib.
_PROVIDENCIAS = {
    "acbrlib_ausente": "a ACBrLib não está instalada no servidor fiscal",
    "sefaz_sem_comunicacao": "sem comunicação com a SEFAZ",
    "comunicador_fora_do_ar": "o serviço fiscal (comunicador ACBrLib) não respondeu",
    "senha_invalida": "a senha do certificado A1 não confere",
    "certificado_vencido": "o certificado A1 está vencido",
    "certificado_invalido": "o certificado A1 não pôde ser lido",
}

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
        falha = FiscalUnavailable(
            f"ACBrLib: {_PROVIDENCIAS['comunicador_fora_do_ar']} ({type(erro).__name__})."
        )
        falha.motivo = "comunicador_fora_do_ar"
        raise falha from None
    return _ler(resposta, _segredos(corpo))


def _segredos(corpo):
    certificado = (corpo or {}).get("certificado") or {}
    return [s for s in (certificado.get("senha"), certificado.get("pfx_base64")) if s]


def _sem_segredo(texto, segredos):
    for segredo in segredos:
        texto = texto.replace(segredo, "***")
    return texto


def _ler(resposta, segredos=()):
    try:
        dados = resposta.json()
    except ValueError:
        dados = {}
    if resposta.status_code in (401, 403):
        raise FiscalConfigurationError(
            "ACBrLib: o comunicador recusou o token (ACBRLIB_TOKEN diferente nos dois lados)."
        )
    # 503 COM `erro` é o comunicador falando (SEFAZ fora); sem, é o proxy na
    # frente dele.
    if resposta.status_code in (502, 503, 504) and not dados.get("erro"):
        raise FiscalUnavailable(f"ACBrLib: comunicador indisponível (HTTP {resposta.status_code}).")
    if resposta.status_code >= 400 or dados.get("erro"):
        familia = _FAMILIAS.get(dados.get("erro"), FiscalAmbiguous)
        mensagem = _sem_segredo(dados.get("mensagem") or f"HTTP {resposta.status_code}", segredos)
        motivo = dados.get("motivo") or ""
        providencia = _PROVIDENCIAS.get(motivo)
        falha = familia(f"ACBrLib: {providencia} — {mensagem}" if providencia else f"ACBrLib: {mensagem}")
        falha.motivo = motivo
        raise falha
    return dados
