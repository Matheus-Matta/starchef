"""O cStat vira a situação certa, e a falha da lib vira a família certa."""
import pytest

from app import sefaz
from app.acbrlib import _classificar, _do_xml


@pytest.mark.parametrize(("cstat", "situacao"), [
    ("100", "autorizada"), ("150", "autorizada"), ("110", "denegada"), ("217", "nao_encontrada"),
    ("103", "processando"), ("135", "cancelada"), ("778", "rejeitada"),
])
def test_cstat_vira_situacao(cstat, situacao):
    assert sefaz.situacao(cstat) == situacao


def test_servico_paralisado_e_indisponibilidade_nao_recusa():
    with pytest.raises(sefaz.FalhaDeComunicacao):
        sefaz.situacao("108")


@pytest.mark.parametrize(("mensagem", "classe"), [
    ("Erro ao carregar o certificado PFX", sefaz.FalhaDeConfiguracao),
    ("Falha na validação do Schema", sefaz.DocumentoInvalido),
    ("Read timed out", sefaz.FalhaIncerta),
    ("Socket Error # 10061 Connection refused", sefaz.FalhaDeComunicacao),
    ("algo que ninguém previu", sefaz.FalhaIncerta),
])
def test_falha_da_lib_vira_a_familia_certa(mensagem, classe):
    assert isinstance(_classificar(mensagem), classe)


def test_le_chave_qr_e_digest_do_xml_assinado():
    xml = ('<NFe><infNFe Id="NFe' + "3" * 44 + '"/><DigestValue>abc=</DigestValue>'
           "<infNFeSupl><qrCode><![CDATA[https://qr?p=1]]></qrCode></infNFeSupl></NFe>")
    assert _do_xml(xml) == {"chave": "3" * 44, "qrcode": "https://qr?p=1", "digest_value": "abc="}
