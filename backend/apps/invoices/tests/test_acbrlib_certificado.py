"""O certificado A1 conferido ANTES de ir ao comunicador, com o motivo pelo nome.

Antes a ACBrLib recusava com a frase técnica dela ("Erro ao carregar o
certificado"), igual para senha errada, arquivo vencido ou certificado de outra
empresa. O operador não sabia o que trocar — e o suporte pedia o arquivo e a
senha para descobrir. Aqui cada caso tem um `motivo` e uma frase própria, e
nenhuma frase (nem o log) carrega o certificado, a senha ou o base64.
"""
import base64
import datetime
import logging

import pytest

from apps.invoices.acbrlib.certificado import conferir_certificado
from apps.invoices.providers_erros import FiscalConfigurationError
from apps.invoices.tests.certificado_de_teste import AGORA, CNPJ, SENHA, pfx

def _motivo(**kwargs):
    with pytest.raises(FiscalConfigurationError) as erro:
        conferir_certificado(cnpj_emitente=CNPJ, agora=AGORA, **kwargs)
    return erro.value


def test_certificado_valido_passa():
    conferir_certificado(pfx(vence=AGORA + datetime.timedelta(days=200)), SENHA, cnpj_emitente=CNPJ, agora=AGORA)


def test_sem_certificado_diz_que_esta_ausente():
    erro = _motivo(pfx_base64="", senha=SENHA)
    assert erro.motivo == "certificado_ausente"
    assert "não tem certificado" in str(erro)


def test_senha_errada_diz_senha_invalida():
    erro = _motivo(pfx_base64=pfx(vence=AGORA + datetime.timedelta(days=200)), senha="outra")
    assert erro.motivo == "senha_invalida"


def test_arquivo_que_nao_e_pfx_diz_certificado_invalido():
    erro = _motivo(pfx_base64=base64.b64encode(b"nao sou um pfx").decode(), senha=SENHA)
    assert erro.motivo == "certificado_invalido"


def test_certificado_vencido_diz_a_data():
    erro = _motivo(pfx_base64=pfx(vence=AGORA - datetime.timedelta(days=3)), senha=SENHA)
    assert erro.motivo == "certificado_vencido"
    assert "10/10/2026" in str(erro)


def test_certificado_de_outra_empresa_diz_cnpj_diferente():
    erro = _motivo(pfx_base64=pfx(cnpj="99888777000166"), senha=SENHA)
    assert erro.motivo == "cnpj_diferente"
    assert "99.888.777/0001-66" in str(erro)


def test_certificado_da_matriz_vale_para_a_filial():
    # A raiz do CNPJ (8 primeiros dígitos) é a mesma: a SEFAZ aceita o A1 da
    # matriz assinando a nota da filial.
    conferir_certificado(pfx(cnpj="11222333000262"), SENHA, cnpj_emitente=CNPJ, agora=AGORA)


def test_nenhuma_mensagem_nem_log_carrega_o_segredo(caplog):
    caplog.set_level(logging.DEBUG)
    conteudo = pfx()
    for kwargs in ({"pfx_base64": conteudo, "senha": "errada-123"},
                   {"pfx_base64": conteudo[:40], "senha": SENHA}):
        erro = _motivo(**kwargs)
        for segredo in (kwargs["senha"], kwargs["pfx_base64"][:20]):
            assert segredo not in str(erro)
            assert segredo not in caplog.text
