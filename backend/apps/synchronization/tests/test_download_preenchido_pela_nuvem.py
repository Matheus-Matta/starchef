"""No download, tamanho e SHA-256 vêm de quem TEM o arquivo.

A loja pede a foto que o painel da nuvem enviou, e para o logo e a foto antiga
do produto ela não sabe nem o tamanho nem o checksum — o registro não guarda.
Exigir os dois de quem pede tornava o download impossível justamente para
esses arquivos.
"""
import hashlib
import uuid
from pathlib import Path

import pytest

from apps.core.storage import media_storage
from apps.synchronization.tests.test_files_api import _cliente

pytestmark = pytest.mark.django_db

FOTO = b"logo-da-loja-" * 300


@pytest.fixture
def disco(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.AWS_STORAGE_BUCKET_NAME = ""
    media_storage.reset()
    yield tmp_path
    media_storage.reset()


def _pedido(caminho, **extra):
    return {"direction": "download", "entity_type": "restaurant", "entity_id": str(uuid.uuid4()),
            "field_name": "logo", "storage_path": caminho, **extra}


def test_download_sem_tamanho_nem_checksum_a_nuvem_preenche(como_nuvem, no_loja, disco):
    caminho = "restaurants/logos/logo.png"
    Path(disco / caminho).parent.mkdir(parents=True)
    Path(disco / caminho).write_bytes(FOTO)

    resposta = _cliente(no_loja).post("/api/v1/sync/files/", _pedido(caminho), format="json")

    assert resposta.status_code == 201, resposta.content
    assert resposta.json()["total_bytes"] == len(FOTO)
    assert resposta.json()["checksum"] == hashlib.sha256(FOTO).hexdigest()


def test_download_do_que_a_nuvem_nao_tem_e_404(como_nuvem, no_loja, disco):
    resposta = _cliente(no_loja).post("/api/v1/sync/files/", _pedido("restaurants/logos/nao.png"), format="json")

    assert resposta.status_code == 404


def test_envio_continua_exigindo_tamanho_e_checksum(como_nuvem, no_loja, disco):
    corpo = {**_pedido("produtos/x.jpg"), "direction": "upload"}

    resposta = _cliente(no_loja).post("/api/v1/sync/files/", corpo, format="json")

    assert resposta.status_code == 400
