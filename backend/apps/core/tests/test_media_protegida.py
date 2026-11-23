"""O certificado A1 não pode ser baixado pela URL de /media/."""

import pytest
from django.test import override_settings

from apps.core.media_protegida import caminho_privado


@pytest.mark.parametrize(
    "path",
    [
        "certificates/12345678000190.pfx",
        "Certificates/12345678000190.pfx",
        "/certificates/x.pfx",
        "imagens/../certificates/x.pfx",
        "%63ertificates/x.pfx",
        r"certificates\x.pfx",
    ],
)
def test_pasta_de_certificados_e_privada(path):
    """Defeito: o .pfx saía sem login em /media/certificates/<CNPJ>.pfx."""
    assert caminho_privado(path)


@pytest.mark.parametrize("path", ["products/a.png", "imagens/certificates-x.png"])
def test_outras_midias_continuam_publicas(path):
    assert not caminho_privado(path)


@pytest.mark.django_db
def test_url_de_certificado_devolve_404(client, tmp_path, settings):
    pasta = tmp_path / "certificates"
    pasta.mkdir()
    (pasta / "12345678000190.pfx").write_bytes(b"segredo")
    settings.MEDIA_ROOT = tmp_path
    resposta = client.get("/media/certificates/12345678000190.pfx")
    assert resposta.status_code == 404
