"""Transferência de binário em pedaços, com retomada e validação (§16).

A sequência é a do plano, e a ordem dela é o que importa:

1. os metadados chegam no evento normal (nome, tamanho, MIME, SHA-256);
2. o conteúdo vem por HTTPS autenticado, em pedaços;
3. cada pedaço é gravado numa **área temporária**, por offset;
4. no fim, tamanho e checksum são conferidos;
5. só então o arquivo é movido **atomicamente** para o destino;
6. e só depois disso o registro é associado a ele.

A área temporária não é zelo excessivo: sem ela, uma queda no meio deixaria um
JPEG truncado no lugar da foto do produto — e o sistema não teria como saber
que aquilo está pela metade. No temporário, um arquivo incompleto é só um
arquivo incompleto.
"""
import logging
import os
from pathlib import Path

from django.conf import settings

from apps.synchronization.models.transfer import SyncFileTransfer, TransferStatus

logger = logging.getLogger(__name__)

#: Tamanho do pedaço. 1 MiB atravessa link ruim sem estourar memória nem
#: limite de corpo do proxy.
CHUNK_BYTES = 1024 * 1024
#: Teto do arquivo aceito. Um upload de 2 GB por engano enche o disco da loja.
MAX_BYTES_PADRAO = 64 * 1024 * 1024
#: Tipos aceitos. O que não está aqui não entra — nem com extensão trocada.
MIME_PERMITIDOS = {
    "image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml",
    "application/pdf", "application/xml", "text/xml", "text/plain",
    "application/octet-stream",
}


class TransferRejected(ValueError):
    """Tamanho, tipo, offset ou checksum fora do combinado."""


class TransferUnavailable(RuntimeError):
    """A área temporária não é gravável, ou o disco acabou.

    Separado de `TransferRejected` porque a culpa é do servidor, não de quem
    enviou: retentar o mesmo pedaço mais tarde é a ação certa. Vira 503, não
    400 — e a mensagem diz o caminho, porque "erro interno" faz alguém abrir o
    código para descobrir que era permissão de volume.
    """


def max_bytes():
    return int(getattr(settings, "SYNC_FILE_MAX_BYTES", MAX_BYTES_PADRAO))


def temp_dir():
    """A área de montagem dos pedaços. Fica DENTRO do MEDIA_ROOT de propósito.

    Montar um volume separado aqui é um convite a erro de permissão: o Docker
    cria o caminho como root quando ele não existe na imagem, e o processo roda
    sem privilégio.
    """
    caminho = Path(getattr(settings, "MEDIA_ROOT", ".")) / "sync_tmp"
    try:
        caminho.mkdir(parents=True, exist_ok=True)
    except OSError as erro:
        raise TransferUnavailable(
            f"Não foi possível criar a área temporária em {caminho}: {erro}"
        ) from erro
    return caminho


def open_transfer(*, account_id, source_node, target_node, entity_type, entity_id,
                  field_name, storage_path, total_bytes, checksum, content_type=""):
    """Abre (ou retoma) uma transferência. Devolve `(transferência, offset)`.

    Retomar é o caminho normal, não a exceção: o mesmo arquivo pedido de novo
    devolve o offset de onde parou, e quem envia continua dali.
    """
    _validar_cabecalho(total_bytes, content_type, storage_path)

    existente = SyncFileTransfer.objects.filter(
        target_node=target_node, storage_path=storage_path, checksum=checksum,
        status__in=list(TransferStatus.ABERTAS),
    ).first()
    if existente is not None:
        return existente, existente.received_bytes

    transferencia = SyncFileTransfer.objects.create(
        account_id=account_id,
        source_node=source_node,
        target_node=target_node,
        entity_type=entity_type,
        entity_id=str(entity_id),
        field_name=field_name,
        storage_path=storage_path,
        content_type=content_type,
        total_bytes=total_bytes,
        checksum=checksum,
        status=TransferStatus.PENDING,
    )
    transferencia.temp_path = str(temp_dir() / f"{transferencia.id}.part")
    transferencia.save(update_fields=["temp_path"])
    return transferencia, 0


def _validar_cabecalho(total_bytes, content_type, storage_path):
    if total_bytes <= 0:
        raise TransferRejected("Tamanho do arquivo precisa ser maior que zero.")
    if total_bytes > max_bytes():
        raise TransferRejected(
            f"Arquivo de {total_bytes} bytes excede o limite de {max_bytes()}."
        )
    if content_type and content_type.split(";")[0].strip() not in MIME_PERMITIDOS:
        raise TransferRejected(f"Tipo de arquivo não permitido: {content_type}")
    _validar_caminho(storage_path)


def _validar_caminho(storage_path):
    """Impede que o caminho escape do MEDIA_ROOT.

    `../../etc/cron.d/x` num campo de caminho é a travessia de diretório
    clássica — e aqui ela escreveria com as permissões do backend.
    """
    if not storage_path or storage_path.startswith(("/", "\\")):
        raise TransferRejected("Caminho de destino inválido.")
    normalizado = os.path.normpath(storage_path).replace("\\", "/")
    if normalizado.startswith("../") or "/../" in normalizado or normalizado == "..":
        raise TransferRejected("Caminho de destino não pode sair da área de mídia.")


def write_chunk(transferencia, offset, dados):
    """Grava um pedaço no offset exato. Devolve o novo offset.

    Um pedaço fora de ordem é recusado em vez de gravado: aceitar offset
    arbitrário deixaria buracos de zeros no meio do arquivo, e o checksum só
    denunciaria isso no fim — depois de transferir tudo à toa.
    """
    if transferencia.status not in TransferStatus.ABERTAS:
        raise TransferRejected(f"Transferência já está em {transferencia.status}.")
    if offset != transferencia.received_bytes:
        raise TransferRejected(
            f"Offset {offset} fora de ordem; esperado {transferencia.received_bytes}."
        )
    novo_total = offset + len(dados)
    if novo_total > transferencia.total_bytes:
        raise TransferRejected(
            f"Pedaço excede o tamanho declarado ({novo_total} > {transferencia.total_bytes})."
        )

    caminho = Path(transferencia.temp_path)
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with open(caminho, "r+b" if caminho.exists() else "wb") as arquivo:
            arquivo.seek(offset)
            arquivo.write(dados)
    except OSError as erro:
        # Permissão de volume, disco cheio, montagem somente-leitura. Nada
        # disso é culpa de quem enviou, e nada disso melhora virando 500.
        raise TransferUnavailable(
            f"Não foi possível gravar o pedaço em {caminho}: {erro}"
        ) from erro

    transferencia.received_bytes = novo_total
    transferencia.status = TransferStatus.RECEIVING
    transferencia.save(update_fields=["received_bytes", "status", "updated_at"])
    return novo_total


def finish(transferencia):
    """Confere, move e associa. A implementação vive em `files_publish`."""
    from apps.synchronization.services import files_publish

    return files_publish.finish(transferencia)


def cleanup_abandoned(horas=48):
    """Remove temporários de transferências que ninguém retomou."""
    from apps.synchronization.services import files_publish

    return files_publish.cleanup_abandoned(horas)


def checksum_of(caminho, bloco=CHUNK_BYTES):
    """SHA-256 lendo em blocos: um arquivo de 60 MB não vai para a memória."""
    import hashlib

    digestor = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for pedaco in iter(lambda: arquivo.read(bloco), b""):
            digestor.update(pedaco)
    return digestor.hexdigest()
