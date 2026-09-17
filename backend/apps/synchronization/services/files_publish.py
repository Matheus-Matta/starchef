"""A publicação: o que acontece DEPOIS de o último pedaço chegar.

Separado de `files.py` porque receber e publicar são dois assuntos. Receber é
gravar bytes num temporário; publicar é decidir que aqueles bytes são
confiáveis, movê-los para o lugar definitivo e só então ligá-los ao registro.

A ordem — validar, mover, associar — é o que impede um JPEG truncado de virar
a foto de um produto.
"""
import logging
import shutil
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from apps.synchronization.models.transfer import SyncFileTransfer, TransferStatus

logger = logging.getLogger(__name__)


def _files():
    """Import tardio: `files` importa este módulo, e o contrário fecharia o ciclo."""
    from apps.synchronization.services import files

    return files


def finish(transferencia):
    """Confere tamanho e checksum e move para o destino. Só então associa.

    Falhar aqui NÃO apaga o temporário: o arquivo truncado é a evidência de
    que a origem mandou algo errado, e apagá-lo esconderia o problema.
    """
    if not transferencia.is_complete:
        raise _files().TransferRejected(
            f"Faltam {transferencia.total_bytes - transferencia.received_bytes} bytes."
        )

    transferencia.status = TransferStatus.VALIDATING
    transferencia.save(update_fields=["status"])

    caminho = Path(transferencia.temp_path)
    tamanho = caminho.stat().st_size
    if tamanho != transferencia.total_bytes:
        return _falhar(transferencia, f"Tamanho final {tamanho} != {transferencia.total_bytes}.")

    calculado = _files().checksum_of(caminho)
    if calculado != transferencia.checksum:
        return _falhar(
            transferencia, f"Checksum divergente: {calculado[:12]} != {transferencia.checksum[:12]}."
        )

    destino = _mover(caminho, transferencia.storage_path)
    with transaction.atomic():
        transferencia.status = TransferStatus.COMPLETED
        transferencia.completed_at = timezone.now()
        transferencia.last_error = ""
        transferencia.save(update_fields=["status", "completed_at", "last_error"])
        _associar(transferencia)
    logger.info("sync-file: %s concluído em %s", transferencia.id, destino)
    return transferencia


def _mover(origem, storage_path):
    """Move para o destino final. Atômico quando o storage é disco local."""
    if getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""):
        # Storage remoto: não há rename atômico. Sobe o arquivo já validado.
        with open(origem, "rb") as arquivo:
            nome = default_storage.save(storage_path, arquivo)
        origem.unlink(missing_ok=True)
        return nome

    destino = Path(settings.MEDIA_ROOT) / storage_path
    destino.parent.mkdir(parents=True, exist_ok=True)
    # `replace` é atômico no mesmo volume: ninguém enxerga o arquivo pela
    # metade no caminho final, nem por um instante.
    shutil.move(str(origem), str(destino))
    return str(destino)


def _associar(transferencia):
    """Aponta o campo do registro para o arquivo — depois de validado."""
    from apps.synchronization.services.registry import registry

    entrada = registry.get(transferencia.entity_type)
    if entrada is None:
        return False
    model = entrada.model
    gerente = getattr(model, "all_objects", model._default_manager)
    instancia = gerente.filter(pk=transferencia.entity_id).first()
    if instancia is None:
        # O registro ainda não chegou. O arquivo está salvo e válido; a
        # associação acontece quando o evento da entidade for aplicado.
        logger.info(
            "sync-file: %s guardado antes do registro %s/%s",
            transferencia.id, transferencia.entity_type, transferencia.entity_id,
        )
        return False
    setattr(instancia, transferencia.field_name, transferencia.storage_path)
    instancia.save(update_fields=[transferencia.field_name])
    return True


def _falhar(transferencia, motivo):
    transferencia.status = TransferStatus.FAILED
    transferencia.attempts += 1
    transferencia.last_error = motivo[:2000]
    transferencia.save(update_fields=["status", "attempts", "last_error"])
    logger.error("sync-file: %s falhou — %s", transferencia.id, motivo)
    raise _files().TransferRejected(motivo)


def cleanup_abandoned(horas=48):
    """Remove temporários de transferências que ninguém retomou."""
    corte = timezone.now() - timezone.timedelta(hours=horas)
    removidas = 0
    for transferencia in SyncFileTransfer.objects.filter(
        status__in=list(TransferStatus.ABERTAS), updated_at__lt=corte
    ):
        if transferencia.temp_path:
            Path(transferencia.temp_path).unlink(missing_ok=True)
        transferencia.status = TransferStatus.FAILED
        transferencia.last_error = f"Abandonada por mais de {horas}h."
        transferencia.save(update_fields=["status", "last_error"])
        removidas += 1
    return removidas
