"""Certificado cadastrado, mas sem o arquivo NESTE servidor.

O cadastro aponta para media/certificates/<nome>.pfx, e o arquivo pode não
existir aqui: enviado em outro servidor, volume de mídia recriado, ou o
container sem a pasta montada. A leitura estourava "No such file or
directory" e a nota parava em "aguardando SEFAZ" — sem nunca chegar ao
empréstimo da nuvem, que é justamente o caminho da loja sem o arquivo.
"""
from types import SimpleNamespace

from apps.invoices.certificate_data import read_certificate_bytes
from apps.invoices.emission_secrets import SegredosDeEmissao


class ArquivoQueSumiu:
    name = "certificates/NEW_CITY_GOURMET_LTDA.pfx"

    def __bool__(self):
        return True

    def open(self, _modo):
        raise FileNotFoundError(2, "No such file or directory", f"/app/media/{self.name}")


def _config():
    return SimpleNamespace(certificate_file=ArquivoQueSumiu(), certificate_ref="",
                           csc_id="", csc_token="", certificate_password="")


def test_arquivo_ausente_e_tratado_como_sem_certificado():
    assert read_certificate_bytes(_config()) == b""


def test_sem_o_arquivo_aqui_vale_o_certificado_emprestado_da_nuvem():
    segredos = SegredosDeEmissao(_config(), emprestado={"certificate_base64": "UEZY"})
    assert segredos.certificate_base64 == "UEZY"
