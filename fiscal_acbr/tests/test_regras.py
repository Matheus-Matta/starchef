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


@pytest.mark.parametrize(("mensagem", "motivo"), [
    ("Senha do certificado inválida", "senha_invalida"),
    ("Certificado vencido em 01/01/2026", "certificado_vencido"),
    ("Erro ao carregar o certificado PFX", "certificado_invalido"),
    ("Socket Error # 10061 Connection refused", "sefaz_sem_comunicacao"),
    ("Falha na validação do Schema", ""),
])
def test_a_falha_diz_o_motivo_pelo_nome(mensagem, motivo):
    """O backend mostra ao operador a providência certa, não a frase da lib."""
    assert _classificar(mensagem).motivo == motivo


def test_sem_a_lib_o_motivo_e_acbrlib_ausente():
    from app.motor import SemLib

    with pytest.raises(sefaz.FalhaDeConfiguracao) as erro:
        SemLib("/app/libs/libacbrnfe64.so").emitir(None)
    assert erro.value.motivo == "acbrlib_ausente"


def test_le_chave_qr_e_digest_do_xml_assinado():
    xml = ('<NFe><infNFe Id="NFe' + "3" * 44 + '"/><DigestValue>abc=</DigestValue>'
           "<infNFeSupl><qrCode><![CDATA[https://qr?p=1]]></qrCode></infNFeSupl></NFe>")
    assert _do_xml(xml) == {"chave": "3" * 44, "qrcode": "https://qr?p=1", "digest_value": "abc="}
