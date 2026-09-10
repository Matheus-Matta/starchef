"""
Armazenamento de mídia: a promessa é que credencial faltando não derruba nada.

O que estes testes travam:

- em desenvolvimento (sem bucket) grava em disco, e é isso;
- com bucket configurado mas SEM credencial, o processo continua de pé — nada
  levanta no import, no boot ou na leitura;
- o erro aparece só na GRAVAÇÃO, como 503 com o nome das variáveis que faltam;
- o upload pela API devolve uma resposta legível, não um traceback do boto3.
"""
import io

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

from apps.core.exceptions import MediaStorageUnavailable
from apps.core.storage import (
    MODE_LOCAL,
    MODE_S3,
    MediaStorageService,
    UnavailableMediaStorage,
    media_storage,
)


@pytest.fixture
def service():
    """Instância nova por teste: o backend é memorizado depois de construído."""
    return MediaStorageService()


# ── Modo local (desenvolvimento) ─────────────────────────────────────────────


def test_sem_bucket_usa_o_disco_local(settings, service):
    settings.AWS_STORAGE_BUCKET_NAME = ""

    assert service.mode == MODE_LOCAL
    assert service.is_ready
    assert service.missing_settings == []
    assert isinstance(service.build_backend(), FileSystemStorage)


def test_modo_local_grava_sem_reclamar(settings, service, tmp_path):
    settings.AWS_STORAGE_BUCKET_NAME = ""
    settings.MEDIA_ROOT = tmp_path

    service.ensure_writable()  # não levanta
    backend = service.build_backend()
    name = backend.save("teste.txt", ContentFile(b"conteudo"))

    assert backend.exists(name)


def test_url_local_sai_relativa_ao_media_url(settings, service, tmp_path):
    settings.AWS_STORAGE_BUCKET_NAME = ""
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"

    backend = service.build_backend()
    name = backend.save("foto.png", ContentFile(b"x"))

    assert backend.url(name).startswith("/media/")


# ── S3 configurado pela metade ───────────────────────────────────────────────


def test_bucket_sem_credencial_nao_quebra_nada(settings, service):
    """O ponto central: nada levanta fora do momento de gravar."""
    settings.AWS_STORAGE_BUCKET_NAME = "starchef-prod"
    settings.AWS_ACCESS_KEY_ID = ""
    settings.AWS_SECRET_ACCESS_KEY = ""

    assert service.mode == MODE_S3
    assert not service.is_ready
    # Construir o backend, consultar e descrever continuam funcionando.
    backend = service.build_backend()
    assert isinstance(backend, UnavailableMediaStorage)
    assert backend.url("qualquer.png") == ""
    assert backend.exists("qualquer.png") is False
    assert service.describe()["mode"] == "s3"


def test_a_mensagem_diz_quais_variaveis_faltam(settings, service):
    settings.AWS_STORAGE_BUCKET_NAME = "starchef-prod"
    settings.AWS_ACCESS_KEY_ID = ""
    settings.AWS_SECRET_ACCESS_KEY = "segredo"

    assert service.missing_settings == ["AWS_ACCESS_KEY_ID"]
    assert "AWS_ACCESS_KEY_ID" in service.unavailable_reason


def test_gravacao_sem_credencial_levanta_503(settings, service):
    settings.AWS_STORAGE_BUCKET_NAME = "starchef-prod"
    settings.AWS_ACCESS_KEY_ID = ""
    settings.AWS_SECRET_ACCESS_KEY = ""

    with pytest.raises(MediaStorageUnavailable) as exc:
        service.ensure_writable()
    assert exc.value.status_code == 503

    # E também pelo caminho normal de gravação de um arquivo.
    with pytest.raises(MediaStorageUnavailable):
        service.build_backend().save("foto.png", ContentFile(b"x"))


def test_checagem_do_django_avisa_mas_nao_derruba(settings):
    """`manage.py check` avisa; o processo continua subindo."""
    from apps.core.checks import check_media_storage

    settings.AWS_STORAGE_BUCKET_NAME = "starchef-prod"
    settings.AWS_ACCESS_KEY_ID = ""
    settings.AWS_SECRET_ACCESS_KEY = ""

    problems = check_media_storage(None)

    assert len(problems) == 1
    assert problems[0].id == "core.W001"
    # Warning, e não Error: Error impediria o `runserver` de subir.
    assert problems[0].level < 40


def test_sem_bucket_a_checagem_fica_calada(settings):
    from apps.core.checks import check_media_storage

    settings.AWS_STORAGE_BUCKET_NAME = ""

    assert check_media_storage(None) == []


# ── Pela API ─────────────────────────────────────────────────────────────────


def _png(name="foto.png"):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "green").save(buffer, format="PNG")
    buffer.seek(0)
    buffer.name = name
    return buffer


# O upload pela API e exercitado pelo logo de categoria de produto
# (`LogoImageMixin` -> `Image.create_from_upload` -> `MediaStorageService`), que
# e o caminho generico de upload do painel. Qualquer endpoint que aceite arquivo
# serve: o que esta sob teste e o SERVICO de armazenamento, nao a rota.
def _upload_logo(client, **extra):
    return client.post(
        "/api/v1/menu/categories/",
        {"name": "Categoria com logo", "logo_upload": _png(), **extra},
        format="multipart",
    )


@pytest.mark.django_db
def test_upload_pela_api_responde_503_legivel(settings, admin_client):
    """O erro chega ao cliente como resposta, não como traceback."""
    settings.AWS_STORAGE_BUCKET_NAME = "starchef-prod"
    settings.AWS_ACCESS_KEY_ID = ""
    settings.AWS_SECRET_ACCESS_KEY = ""
    media_storage.reset()

    try:
        response = _upload_logo(admin_client)

        assert response.status_code == 503, response.data
        assert "AWS_ACCESS_KEY_ID" in str(response.data)
    finally:
        media_storage.reset()


@pytest.mark.django_db
def test_upload_funciona_no_modo_local(settings, admin_client, tmp_path):
    settings.AWS_STORAGE_BUCKET_NAME = ""
    settings.MEDIA_ROOT = tmp_path
    media_storage.reset()

    try:
        response = _upload_logo(admin_client)

        assert response.status_code == 201, response.data
        assert response.data["logo_url"].endswith(".png")
        assert "/media/" in response.data["logo_url"]
    finally:
        media_storage.reset()
