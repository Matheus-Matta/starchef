"""A falha do comunicador chega ao backend com o motivo pelo nome, sem segredo.

O comunicador manda `motivo` (`acbrlib_ausente`, `sefaz_sem_comunicacao`,
`senha_invalida`...). O backend o guarda na exceção e põe a providência na
frase gravada na nota. E se a frase da lib ecoar a senha ou o certificado
enviados, eles saem da mensagem antes de ela ser gravada ou logada.
"""
from types import SimpleNamespace

import pytest

from apps.invoices.acbrlib import cliente
from apps.invoices.providers_erros import FiscalConfigurationError, FiscalUnavailable


@pytest.fixture(autouse=True)
def _url(settings):
    settings.ACBRLIB_URL = "http://acbr.local"
    settings.ACBRLIB_TOKEN = ""


def _responder(monkeypatch, status, corpo):
    monkeypatch.setattr(
        "apps.invoices.acbrlib.cliente.requests.request",
        lambda *a, **k: SimpleNamespace(status_code=status, json=lambda: corpo),
    )


def test_acbrlib_ausente_diz_o_motivo(monkeypatch):
    _responder(monkeypatch, 500, {"erro": "configuracao", "motivo": "acbrlib_ausente",
                                  "mensagem": "ACBrLib não instalada: copie a lib."})
    with pytest.raises(FiscalConfigurationError) as erro:
        cliente.chamar("/v1/nfe/emitir", {})
    assert erro.value.motivo == "acbrlib_ausente"
    assert "ACBrLib não instalada" in str(erro.value)


def test_sefaz_sem_comunicacao_diz_o_motivo(monkeypatch):
    _responder(monkeypatch, 503, {"erro": "sem_comunicacao", "motivo": "sefaz_sem_comunicacao",
                                  "mensagem": "Socket Error"})
    with pytest.raises(FiscalUnavailable) as erro:
        cliente.chamar("/v1/nfe/emitir", {})
    assert erro.value.motivo == "sefaz_sem_comunicacao"
    assert "SEFAZ" in str(erro.value)


def test_comunicador_fora_do_ar_e_falha_de_comunicacao(monkeypatch):
    import requests

    def cair(*_a, **_k):
        raise requests.ConnectionError("recusado")

    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", cair)
    with pytest.raises(FiscalUnavailable) as erro:
        cliente.chamar("/v1/nfe/emitir", {})
    assert erro.value.motivo == "comunicador_fora_do_ar"


def test_a_mensagem_nunca_carrega_a_senha_nem_o_certificado(monkeypatch):
    corpo = {"certificado": {"pfx_base64": "TUlJS0JBU0U2NENFUlRJRklDQURP", "senha": "s3nh4-xyz"}}
    _responder(monkeypatch, 500, {
        "erro": "configuracao", "motivo": "senha_invalida",
        "mensagem": "Senha s3nh4-xyz inválida para TUlJS0JBU0U2NENFUlRJRklDQURP",
    })
    with pytest.raises(FiscalConfigurationError) as erro:
        cliente.chamar("/v1/nfe/emitir", corpo)
    assert "s3nh4-xyz" not in str(erro.value)
    assert "TUlJS0JBU0U2NENFUlRJRklDQURP" not in str(erro.value)
    assert erro.value.motivo == "senha_invalida"
