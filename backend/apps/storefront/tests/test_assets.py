"""Upload das imagens do editor: validação de conteúdo, escopo e permissão."""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.storefront.models import MenuAsset
from apps.storefront.tests.conftest import authenticated_client

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_temporaria(settings, tmp_path):
    """Uploads de teste não podem sujar o MEDIA_ROOT do projeto."""
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def _png_bytes(size=(20, 10)):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_upload_de_imagem_devolve_url_e_dimensoes(ecommerce_client, ecommerce_account, restaurant):
    upload = SimpleUploadedFile("banner da home.png", _png_bytes(), content_type="image/png")
    response = ecommerce_client.post(
        "/api/v1/storefront/assets/",
        {"file": upload, "restaurant": str(restaurant.id)},
        format="multipart",
    )
    assert response.status_code == 201
    assert response.data["url"]
    assert response.data["width"] == 20
    assert response.data["height"] == 10
    assert response.data["content_type"] == "image/png"
    assert response.data["checksum"]

    asset = MenuAsset.all_objects.get(id=response.data["id"])
    assert asset.account_id == ecommerce_account.id
    assert asset.restaurant_id == restaurant.id
    # O nome no storage é um UUID; o nome escolhido pelo usuário fica só como rótulo.
    assert "banner da home" not in asset.file.name
    assert asset.original_name == "banner da home.png"


def test_arquivo_que_nao_e_imagem_e_recusado(ecommerce_client, restaurant):
    """Renomear um executável para .png não basta: o arquivo é aberto e conferido."""
    upload = SimpleUploadedFile("payload.png", b"MZ\x90\x00 nao sou imagem", content_type="image/png")
    response = ecommerce_client.post(
        "/api/v1/storefront/assets/",
        {"file": upload, "restaurant": str(restaurant.id)},
        format="multipart",
    )
    assert response.status_code == 400
    assert not MenuAsset.all_objects.exists()


def test_extensao_fora_da_lista_e_recusada(ecommerce_client, restaurant):
    upload = SimpleUploadedFile("script.svg", b"<svg onload='alert(1)'></svg>", content_type="image/svg+xml")
    response = ecommerce_client.post(
        "/api/v1/storefront/assets/",
        {"file": upload, "restaurant": str(restaurant.id)},
        format="multipart",
    )
    assert response.status_code == 400


def test_arquivo_acima_do_limite_e_recusado(settings, ecommerce_client, restaurant):
    settings.STOREFRONT_ASSET_MAX_BYTES = 100
    upload = SimpleUploadedFile("grande.png", _png_bytes((400, 400)), content_type="image/png")
    response = ecommerce_client.post(
        "/api/v1/storefront/assets/",
        {"file": upload, "restaurant": str(restaurant.id)},
        format="multipart",
    )
    assert response.status_code == 400


def test_garcom_nao_envia_imagem(waiter_user, restaurant):
    client = authenticated_client(waiter_user)
    upload = SimpleUploadedFile("banner.png", _png_bytes(), content_type="image/png")
    response = client.post(
        "/api/v1/storefront/assets/",
        {"file": upload, "restaurant": str(restaurant.id)},
        format="multipart",
    )
    assert response.status_code == 403


def test_imagens_de_outra_conta_nao_aparecem_na_listagem(ecommerce_client, ecommerce_account, restaurant, other_account_setup):
    MenuAsset.all_objects.create(
        account=other_account_setup["account"],
        restaurant=other_account_setup["restaurant"],
        file="storefront/x/alheia.png",
        original_name="alheia.png",
    )
    minha = MenuAsset.all_objects.create(
        account=ecommerce_account,
        restaurant=restaurant,
        file="storefront/y/minha.png",
        original_name="minha.png",
    )

    response = ecommerce_client.get("/api/v1/storefront/assets/")
    assert response.status_code == 200
    assert [row["id"] for row in response.data["results"]] == [str(minha.id)]
