"""Servir /media/ sem entregar o que é segredo.

O certificado A1 (.pfx) mora em `media/certificates/<CNPJ>.pfx` e o CNPJ sai em
toda nota fiscal — qualquer um adivinhava o endereço e baixava o arquivo sem
login. O backend lê o certificado pelo storage (nunca pela URL), então
nenhuma tela precisa que essa pasta seja pública: ela simplesmente não é
servida.
"""

import posixpath
from urllib.parse import unquote

from django.http import Http404
from django.views.static import serve

# Pastas de media que nunca saem pela URL. Em minúsculas, comparadas sem
# diferenciar maiúscula: em disco case-insensitive (Windows/macOS)
# `/media/Certificates/x.pfx` abriria o mesmo arquivo.
PASTAS_PRIVADAS = ("certificates",)


def caminho_privado(path):
    # Normaliza antes de comparar: `a/../certificates/x.pfx` e `%2e%2e`
    # chegariam à pasta sem começar por ela.
    limpo = posixpath.normpath(unquote(path).replace("\\", "/")).lstrip("/")
    primeira = limpo.split("/", 1)[0].strip().lower()
    return primeira in PASTAS_PRIVADAS


def servir_media(request, path, document_root=None, **kwargs):
    # 404 e não 403: não confirma que o arquivo existe.
    if caminho_privado(path):
        raise Http404("Not found")
    return serve(request, path, document_root=document_root, **kwargs)
