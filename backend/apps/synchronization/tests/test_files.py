"""Transferência de binário: pedaços, retomada, checksum e travessia (§16)."""
import hashlib
import uuid

import pytest

from apps.synchronization.models.transfer import SyncFileTransfer, TransferStatus
from apps.synchronization.services import files

pytestmark = pytest.mark.django_db

CONTEUDO = b"conteudo-de-teste-" * 1000  # ~18 KB
CHECKSUM = hashlib.sha256(CONTEUDO).hexdigest()


def _abrir(conta, origem, destino, *, caminho="produtos/foto.jpg", total=None, checksum=None):
    return files.open_transfer(
        account_id=conta.id, source_node=origem, target_node=destino,
        entity_type="image", entity_id=uuid.uuid4(), field_name="file",
        storage_path=caminho, total_bytes=total or len(CONTEUDO),
        checksum=checksum or CHECKSUM, content_type="image/jpeg",
    )


def test_transferencia_completa_em_pedacos(como_loja, conta, no_nuvem, no_loja, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    transferencia, offset = _abrir(conta, no_nuvem, no_loja)
    assert offset == 0

    pedaco = 4096
    while offset < len(CONTEUDO):
        offset = files.write_chunk(transferencia, offset, CONTEUDO[offset:offset + pedaco])

    files.finish(transferencia)
    transferencia.refresh_from_db()
    assert transferencia.status == TransferStatus.COMPLETED
    destino = tmp_path / "produtos" / "foto.jpg"
    assert destino.exists() and destino.read_bytes() == CONTEUDO


def test_retomada_devolve_o_offset_de_onde_parou(como_loja, conta, no_nuvem, no_loja, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    transferencia, _ = _abrir(conta, no_nuvem, no_loja)
    files.write_chunk(transferencia, 0, CONTEUDO[:5000])

    # A conexão caiu; o remetente pergunta de novo pelo mesmo arquivo.
    mesma, offset = _abrir(conta, no_nuvem, no_loja)
    assert mesma.id == transferencia.id
    assert offset == 5000  # continua daqui, não do zero


def test_pedaco_fora_de_ordem_e_recusado(como_loja, conta, no_nuvem, no_loja, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    transferencia, _ = _abrir(conta, no_nuvem, no_loja)
    files.write_chunk(transferencia, 0, CONTEUDO[:1000])

    # Pular para 5000 deixaria um buraco de zeros que só o checksum acusaria.
    with pytest.raises(files.TransferRejected, match="fora de ordem"):
        files.write_chunk(transferencia, 5000, CONTEUDO[5000:6000])


def test_checksum_divergente_nao_publica_o_arquivo(como_loja, conta, no_nuvem, no_loja, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    transferencia, _ = _abrir(conta, no_nuvem, no_loja, checksum="0" * 64)
    files.write_chunk(transferencia, 0, CONTEUDO)

    with pytest.raises(files.TransferRejected, match="Checksum"):
        files.finish(transferencia)

    transferencia.refresh_from_db()
    assert transferencia.status == TransferStatus.FAILED
    # O arquivo NÃO foi para a pasta de mídia.
    assert not (tmp_path / "produtos" / "foto.jpg").exists()


def test_arquivo_incompleto_nao_e_publicado(como_loja, conta, no_nuvem, no_loja, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    transferencia, _ = _abrir(conta, no_nuvem, no_loja)
    files.write_chunk(transferencia, 0, CONTEUDO[:100])

    with pytest.raises(files.TransferRejected, match="Faltam"):
        files.finish(transferencia)
    assert not (tmp_path / "produtos" / "foto.jpg").exists()


def test_pedaco_maior_que_o_declarado_e_recusado(como_loja, conta, no_nuvem, no_loja, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    transferencia, _ = _abrir(conta, no_nuvem, no_loja, total=100)
    with pytest.raises(files.TransferRejected, match="excede o tamanho"):
        files.write_chunk(transferencia, 0, CONTEUDO)


def test_travessia_de_diretorio_e_bloqueada(como_loja, conta, no_nuvem, no_loja):
    """`../../etc/cron.d/x` escreveria com a permissão do backend."""
    for caminho in ("../../etc/passwd", "/etc/passwd", "produtos/../../fora.txt"):
        with pytest.raises(files.TransferRejected):
            _abrir(conta, no_nuvem, no_loja, caminho=caminho)


def test_tipo_nao_permitido_e_recusado(como_loja, conta, no_nuvem, no_loja):
    with pytest.raises(files.TransferRejected, match="não permitido"):
        files.open_transfer(
            account_id=conta.id, source_node=no_nuvem, target_node=no_loja,
            entity_type="image", entity_id=uuid.uuid4(), field_name="file",
            storage_path="x.exe", total_bytes=10, checksum=CHECKSUM,
            content_type="application/x-msdownload",
        )


def test_arquivo_grande_demais_e_recusado(como_loja, conta, no_nuvem, no_loja, settings):
    settings.SYNC_FILE_MAX_BYTES = 1024
    with pytest.raises(files.TransferRejected, match="excede o limite"):
        _abrir(conta, no_nuvem, no_loja, total=99999)


def test_limpeza_de_abandonadas(como_loja, conta, no_nuvem, no_loja, settings, tmp_path):
    from django.utils import timezone

    settings.MEDIA_ROOT = str(tmp_path)
    transferencia, _ = _abrir(conta, no_nuvem, no_loja)
    files.write_chunk(transferencia, 0, CONTEUDO[:10])
    SyncFileTransfer.objects.filter(pk=transferencia.pk).update(
        updated_at=timezone.now() - timezone.timedelta(hours=72)
    )

    assert files.cleanup_abandoned(horas=48) == 1
    transferencia.refresh_from_db()
    assert transferencia.status == TransferStatus.FAILED
