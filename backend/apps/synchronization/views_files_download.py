"""O lado de BAIXAR: a loja puxa da nuvem o binário que o evento anunciou.

Separado do upload porque o mecanismo é o oposto — aqui quem controla o offset
é quem recebe, e o servidor só serve a fatia pedida. É o que permite retomar
uma foto de 4 MB que caiu aos 3,5 MB sem recomeçar.
"""
import logging
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

#: Quanto servir por requisição de download.
FATIA_BYTES = 1024 * 1024


class DownloadMixin:
    """`GET .../download/?offset=N` — serve a fatia a partir de N."""

    def download(self, request, transferencia):
        caminho = transferencia.storage_path
        try:
            offset = max(0, int(request.query_params.get("offset", 0)))
        except ValueError:
            return HttpResponse("offset inválido", status=400)

        if getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""):
            return self._do_storage(caminho, offset, transferencia)
        return self._do_disco(caminho, offset, transferencia)

    def _do_disco(self, caminho, offset, transferencia):
        arquivo = Path(settings.MEDIA_ROOT) / caminho
        if not arquivo.exists():
            raise Http404
        tamanho = arquivo.stat().st_size
        if offset >= tamanho:
            return self._resposta(b"", offset, tamanho, transferencia)

        with open(arquivo, "rb") as origem:
            origem.seek(offset)
            dados = origem.read(FATIA_BYTES)
        return self._resposta(dados, offset, tamanho, transferencia)

    def _do_storage(self, caminho, offset, transferencia):
        """Storage remoto: sem seek barato, lê e descarta até o offset.

        Aceitável porque o caminho normal é disco local; quem usa bucket
        costuma servir a mídia direto dele, sem passar por aqui.
        """
        if not default_storage.exists(caminho):
            raise Http404
        tamanho = default_storage.size(caminho)
        with default_storage.open(caminho, "rb") as origem:
            origem.seek(offset) if hasattr(origem, "seek") else origem.read(offset)
            dados = origem.read(FATIA_BYTES)
        return self._resposta(dados, offset, tamanho, transferencia)

    def _resposta(self, dados, offset, tamanho, transferencia):
        resposta = HttpResponse(dados, content_type="application/octet-stream")
        resposta["X-Sync-Offset"] = str(offset)
        resposta["X-Sync-Total-Bytes"] = str(tamanho)
        resposta["X-Sync-Checksum"] = transferencia.checksum
        # Diz se acabou sem o cliente ter de comparar números.
        resposta["X-Sync-Complete"] = "1" if offset + len(dados) >= tamanho else "0"
        return resposta
