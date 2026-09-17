"""O lado da LOJA na transferência de arquivo: empurra e puxa binário.

A retomada é a razão de este módulo existir. Numa conexão de restaurante, uma
foto de produto de 4 MB não chega inteira na primeira tentativa com frequência
suficiente para que "recomeçar do zero" signifique "nunca chegar".
"""
import logging
from pathlib import Path

import requests
from django.conf import settings

from apps.synchronization.services import files, nodes

logger = logging.getLogger(__name__)

TIMEOUT = 120
CAMINHO = "/api/v1/sync/files/"


class TransferError(RuntimeError):
    """A outra ponta recusou ou não respondeu."""


def _cabecalhos(no):
    return {
        "Authorization": f"Bearer {getattr(settings, 'SYNC_AUTH_TOKEN', '')}",
        "X-Sync-Node-Id": str(no.id),
    }


def _base():
    url = getattr(settings, "SYNC_CLOUD_API_URL", "")
    if not url:
        raise TransferError("SYNC_CLOUD_API_URL não configurada.")
    return url.rstrip("/") + CAMINHO


def push(caminho_local, *, entity_type, entity_id, field_name, storage_path,
         content_type="", chunk=None):
    """Envia um arquivo para a nuvem, retomando de onde parou.

    Devolve o corpo final da transferência. Levanta `TransferError` em qualquer
    recusa — quem chama decide se tenta de novo agora ou depois.
    """
    arquivo = Path(caminho_local)
    if not arquivo.exists():
        raise TransferError(f"Arquivo não encontrado: {caminho_local}")

    tamanho = arquivo.stat().st_size
    checksum = files.checksum_of(arquivo)
    no = nodes.self_node()
    cabecalhos = _cabecalhos(no)
    pedaco = chunk or files.CHUNK_BYTES

    abertura = _post(_base(), cabecalhos, {
        "direction": "upload",
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "field_name": field_name,
        "storage_path": storage_path,
        "total_bytes": tamanho,
        "checksum": checksum,
        "content_type": content_type,
    })
    transfer_id = abertura["id"]
    offset = int(abertura.get("offset", 0))
    if offset:
        logger.info("sync-file: retomando %s a partir de %s bytes", storage_path, offset)

    with open(arquivo, "rb") as origem:
        origem.seek(offset)
        while offset < tamanho:
            dados = origem.read(pedaco)
            if not dados:
                break
            offset = _enviar_pedaco(transfer_id, cabecalhos, offset, dados)

    return _post(f"{_base()}{transfer_id}/complete/", cabecalhos, {})


def _enviar_pedaco(transfer_id, cabecalhos, offset, dados):
    """Envia um pedaço. Um 409 devolve o offset certo em vez de falhar."""
    resposta = requests.put(
        f"{_base()}{transfer_id}/chunk/",
        data=dados,
        headers={**cabecalhos, "X-Sync-Offset": str(offset),
                 "Content-Type": "application/octet-stream"},
        timeout=TIMEOUT,
    )
    if resposta.status_code == 409:
        # O servidor já tinha mais (ou menos) do que pensávamos. Realinha em
        # vez de desistir — é o caso normal depois de um timeout de rede em que
        # o pedaço chegou mas a resposta não.
        #
        # Lê do CABEÇALHO: o corpo passa pelo envelope de erro da API e muda de
        # forma conforme o status. O cabeçalho não muda.
        esperado = int(resposta.headers.get("X-Sync-Expected-Offset", offset))
        logger.info("sync-file: realinhando offset %s -> %s", offset, esperado)
        return esperado
    if resposta.status_code >= 400:
        raise TransferError(f"Pedaço recusado ({resposta.status_code}): {resposta.text[:200]}")
    return int(resposta.json()["offset"])


def pull(transfer_id, destino_local, *, chunk=None):
    """Baixa um arquivo da nuvem, retomando pelo que já existe em disco."""
    no = nodes.self_node()
    cabecalhos = _cabecalhos(no)
    destino = Path(destino_local)
    destino.parent.mkdir(parents=True, exist_ok=True)

    offset = destino.stat().st_size if destino.exists() else 0
    esperado_checksum, total = None, None

    while True:
        resposta = requests.get(
            f"{_base()}{transfer_id}/download/", params={"offset": offset},
            headers=cabecalhos, timeout=TIMEOUT,
        )
        if resposta.status_code >= 400:
            raise TransferError(f"Download recusado ({resposta.status_code}).")

        esperado_checksum = resposta.headers.get("X-Sync-Checksum", esperado_checksum)
        total = int(resposta.headers.get("X-Sync-Total-Bytes", total or 0))
        dados = resposta.content
        if dados:
            with open(destino, "r+b" if destino.exists() else "wb") as arquivo:
                arquivo.seek(offset)
                arquivo.write(dados)
            offset += len(dados)
        if resposta.headers.get("X-Sync-Complete") == "1" or not dados:
            break

    _conferir(destino, offset, total, esperado_checksum)
    return destino


def _conferir(destino, recebido, total, esperado_checksum):
    """Tamanho e checksum antes de qualquer uso. Errado, o arquivo some.

    Aqui o incompleto é apagado — ao contrário do lado servidor, onde ele é
    evidência. Neste lado o arquivo iria direto para a pasta de mídia, e um
    JPEG truncado ali é pior do que arquivo nenhum.
    """
    if total and recebido != total:
        destino.unlink(missing_ok=True)
        raise TransferError(f"Download incompleto: {recebido} de {total} bytes.")
    if esperado_checksum:
        calculado = files.checksum_of(destino)
        if calculado != esperado_checksum:
            destino.unlink(missing_ok=True)
            raise TransferError(
                f"Checksum divergente: {calculado[:12]} != {esperado_checksum[:12]}."
            )


def _post(url, cabecalhos, corpo):
    try:
        resposta = requests.post(url, json=corpo, headers=cabecalhos, timeout=TIMEOUT)
    except requests.RequestException as erro:
        raise TransferError(f"Falha ao falar com a nuvem: {erro}") from erro
    if resposta.status_code >= 400:
        raise TransferError(f"Recusado ({resposta.status_code}): {resposta.text[:300]}")
    return resposta.json()
