"""A foto enviada na loja chega à nuvem — e a da nuvem chega à loja.

O defeito: a loja gravava a imagem no disco dela e o evento levava à nuvem só
o caminho. O link da nuvem (`https://api.starchef.com.br/media/accounts/...`)
dava 404, porque o arquivo nunca saía da loja: a transferência em pedaços
existia e ninguém a chamava. A rede é trocada por uma nuvem de mentira; o resto
— achar os arquivos, decidir o sentido, registrar, não repetir — é o de verdade.
"""
import hashlib
from pathlib import Path

import pytest
from django.core.files.base import ContentFile

from apps.core.storage import media_storage
from apps.images.models import Image
from apps.synchronization.models.transfer import SyncFileTransfer, TransferStatus
from apps.synchronization.services import files_client, midia, midia_envio

pytestmark = pytest.mark.django_db

FOTO = b"\xff\xd8\xff-jpeg-de-teste-" * 64


@pytest.fixture
def disco(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.AWS_STORAGE_BUCKET_NAME = ""
    settings.SYNC_CLOUD_API_URL = "https://nuvem.test"
    media_storage.reset()
    yield tmp_path
    media_storage.reset()


@pytest.fixture
def nuvem_de_mentira(monkeypatch):
    """O que a nuvem recebeu e o que ela tem para entregar."""
    recebido, tem = [], {}

    def push(caminho, *, storage_path, **_):
        dados = Path(caminho).read_bytes()
        recebido.append(storage_path)
        return {"total_bytes": len(dados), "checksum": hashlib.sha256(dados).hexdigest()}

    def abrir(_url, _cabecalhos, corpo):
        if corpo["storage_path"] not in tem:
            raise files_client.TransferError("Recusado (404): arquivo_ausente")
        dados = tem[corpo["storage_path"]]
        return {"id": "t-" + corpo["entity_id"], "total_bytes": len(dados),
                "checksum": hashlib.sha256(dados).hexdigest(), "_caminho": corpo["storage_path"]}

    pedidos = {}

    def abrir_e_lembrar(url, cabecalhos, corpo):
        resposta = abrir(url, cabecalhos, corpo)
        pedidos[resposta["id"]] = resposta["_caminho"]
        return resposta

    def pull(transfer_id, destino):
        Path(destino).parent.mkdir(parents=True, exist_ok=True)
        Path(destino).write_bytes(tem[pedidos[transfer_id]])
        return destino

    monkeypatch.setattr(files_client, "push", push)
    monkeypatch.setattr(files_client, "_post", abrir_e_lembrar)
    monkeypatch.setattr(files_client, "pull", pull)
    return {"recebido": recebido, "tem": tem}


def _foto(conta, nome="prato.jpg", conteudo=FOTO):
    imagem = Image(account=conta, original_name=nome, content_type="image/jpeg",
                   size=len(conteudo), checksum=hashlib.sha256(conteudo).hexdigest())
    imagem.file.save(nome, ContentFile(conteudo), save=False)
    imagem.save()
    return imagem


def test_foto_que_so_a_loja_tem_sobe_para_a_nuvem_no_mesmo_caminho(como_loja, conta, disco, nuvem_de_mentira):
    foto = _foto(conta)

    conta_da_rodada = midia_envio.rodada()

    assert nuvem_de_mentira["recebido"] == [foto.file.name]
    assert conta_da_rodada["enviados"] == 1
    assert SyncFileTransfer.objects.filter(entity_id=str(foto.pk), status=TransferStatus.COMPLETED).exists()


def test_foto_ja_enviada_nao_sobe_de_novo_a_cada_rodada(como_loja, conta, disco, nuvem_de_mentira):
    _foto(conta)
    midia_envio.rodada()

    segunda = midia_envio.rodada()

    assert len(nuvem_de_mentira["recebido"]) == 1
    assert segunda["enviados"] == 0 and segunda["ja_em_dia"] == 1


def test_foto_que_so_a_nuvem_tem_e_baixada_para_a_loja(como_loja, conta, disco, nuvem_de_mentira):
    foto = _foto(conta)
    caminho = foto.file.name
    (disco / caminho).unlink()  # enviada pelo painel da nuvem: aqui só chegou o registro
    nuvem_de_mentira["tem"][caminho] = FOTO

    resultado = midia_envio.rodada()

    assert resultado["baixados"] == 1
    assert (disco / caminho).read_bytes() == FOTO
    assert midia.existe_aqui(caminho)


def test_arquivo_que_falta_nos_dois_lados_espera_em_vez_de_tentar_toda_rodada(
    como_loja, conta, disco, nuvem_de_mentira,
):
    foto = _foto(conta)
    (disco / foto.file.name).unlink()

    primeira = midia_envio.rodada()
    segunda = midia_envio.rodada()

    assert primeira["falhas"] == 1
    assert segunda["falhas"] == 0 and segunda["ja_em_dia"] == 1
    assert SyncFileTransfer.objects.get(entity_id=str(foto.pk)).status == TransferStatus.FAILED


def test_campos_de_midia_trazem_as_fotos_e_nunca_o_certificado():
    campos = {f"{entrada.entity_type}.{campo}" for entrada, campo in midia.campos_de_midia()}

    assert "image.file" in campos
    assert "restaurant.logo" in campos
    assert not any(campo.endswith("certificate_file") for campo in campos)
