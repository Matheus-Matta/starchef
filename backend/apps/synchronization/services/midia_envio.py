"""A rodada da LOJA: sobe o arquivo que só ela tem e baixa o que só a nuvem tem.

Os dois sentidos, porque a foto nasce nos dois lugares: no PDV ou no painel da
loja, e no painel da nuvem. Cada arquivo vai pelo canal em pedaços que já
existia (`files_client.push`/`pull`): retomável, com tamanho e SHA-256
conferidos antes de virar a foto do produto.

O arquivo chega no MESMO caminho do registro. É isso que conserta o link: ele
é montado do caminho, então a imagem da loja passa a abrir na nuvem sem
ninguém mexer no cadastro.
"""
import logging
import mimetypes
import shutil
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage

from apps.synchronization.models.transfer import TransferStatus
from apps.synchronization.services import files, files_client, midia, nodes

logger = logging.getLogger(__name__)


def rodada(*, limite=50, forcar=False):
    """Uma passada por todos os arquivos de mídia. Devolve a contagem.

    `limite` segura a rodada periódica (a primeira, numa loja com centenas de
    fotos, não pode ocupar o worker por uma hora); o comando manual passa
    `None`. `forcar` reenvia até o que já consta como enviado.
    """
    proprio = nodes.self_node()
    nuvem = proprio.peer
    conta = {"enviados": 0, "baixados": 0, "falhas": 0, "ja_em_dia": 0}
    if nuvem is None:
        logger.warning("sync-midia: este nó não tem a nuvem como par; nada a fazer")
        return conta
    for entrada, campo in midia.campos_de_midia():
        for instancia in midia.registros_com_arquivo(entrada, campo).iterator():
            if limite is not None and conta["enviados"] + conta["baixados"] + conta["falhas"] >= limite:
                return conta
            _um(entrada, instancia, campo, proprio, nuvem, conta, forcar)
    return conta


def _um(entrada, instancia, campo, proprio, nuvem, conta, forcar):
    caminho = getattr(instancia, campo).name
    aqui = midia.existe_aqui(caminho)
    if not forcar and (midia.ja_transferido(entrada, instancia.pk, campo, caminho)
                       or midia.falhou_ha_pouco(entrada, instancia.pk, campo, caminho)):
        conta["ja_em_dia"] += 1
        return
    origem, destino = (proprio, nuvem) if aqui else (nuvem, proprio)
    try:
        total, checksum = (enviar if aqui else baixar)(entrada, instancia, campo, caminho)
    except (files_client.TransferError, files.TransferRejected, OSError) as erro:
        logger.warning("sync-midia: %s %s falhou — %s", "envio" if aqui else "download", caminho, erro)
        midia.registrar(entrada, instancia, campo, caminho, origem=origem, destino=destino,
                        status=TransferStatus.FAILED, erro=str(erro))
        conta["falhas"] += 1
        return
    midia.registrar(entrada, instancia, campo, caminho, origem=origem, destino=destino,
                    status=TransferStatus.COMPLETED, total_bytes=total, checksum=checksum)
    conta["enviados" if aqui else "baixados"] += 1
    logger.info("sync-midia: %s %s", "enviado" if aqui else "baixado", caminho)


def enviar(entrada, instancia, campo, caminho):
    """Sobe para a nuvem. Devolve `(bytes, sha256)` do que ela conferiu."""
    with _no_disco(caminho) as arquivo:
        corpo = files_client.push(
            arquivo, entity_type=entrada.entity_type, entity_id=instancia.pk,
            field_name=campo, storage_path=caminho,
            content_type=mimetypes.guess_type(caminho)[0] or "",
        )
    return int(corpo.get("total_bytes") or 0), corpo.get("checksum", "")


def baixar(entrada, instancia, campo, caminho):
    """Baixa da nuvem para o mesmo caminho. A nuvem informa tamanho e SHA-256."""
    no = nodes.self_node()
    abertura = files_client._post(files_client._base(), files_client._cabecalhos(no), {
        "direction": "download", "entity_type": entrada.entity_type,
        "entity_id": str(instancia.pk), "field_name": campo, "storage_path": caminho,
    })
    temporario = files.temp_dir() / f"baixando-{abertura['id']}.part"
    files_client.pull(abertura["id"], temporario)
    _publicar(temporario, caminho)
    return int(abertura.get("total_bytes") or 0), abertura.get("checksum", "")


def _publicar(temporario, caminho):
    """Do temporário (já conferido) para o caminho do registro."""
    if getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""):
        with open(temporario, "rb") as arquivo:
            default_storage.save(caminho, File(arquivo))
        Path(temporario).unlink(missing_ok=True)
        return
    destino = Path(settings.MEDIA_ROOT) / caminho
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(temporario), str(destino))


class _no_disco:
    """O arquivo como caminho de disco: direto do MEDIA_ROOT ou copiado do bucket."""

    def __init__(self, caminho):
        self.caminho, self._copia = caminho, None

    def __enter__(self):
        local = Path(settings.MEDIA_ROOT) / self.caminho
        if not getattr(settings, "AWS_STORAGE_BUCKET_NAME", "") and local.exists():
            return local
        self._copia = files.temp_dir() / f"enviando-{Path(self.caminho).name}"
        with default_storage.open(self.caminho, "rb") as origem, open(self._copia, "wb") as copia:
            shutil.copyfileobj(origem, copia)
        return self._copia

    def __exit__(self, *_):
        if self._copia is not None:
            Path(self._copia).unlink(missing_ok=True)
