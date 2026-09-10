from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image as PillowImage

from apps.images.models import Image, ProductImage
from apps.menu.models import Product, ProductVariation

pytestmark = pytest.mark.django_db


def png(name, color="red"):
    buffer = BytesIO()
    PillowImage.new("RGB", (12, 8), color=color).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def jpeg(name, color="red"):
    buffer = BytesIO()
    PillowImage.new("RGB", (12, 8), color=color).save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def disguised_jpeg():
    buffer = BytesIO()
    PillowImage.new("RGB", (8, 8), color="red").save(buffer, format="JPEG")
    return SimpleUploadedFile("disfarce.png", buffer.getvalue(), content_type="image/png")


def product_payload(restaurant, branch, **extra):
    payload = {
        "name": "Produto com fotos",
        "internal_code": "IMG-1",
        "sale_price": "12.00",
        "restaurant": str(restaurant.id),
        "branch": str(branch.id),
        "restaurants": [str(restaurant.id)],
    }
    payload.update(extra)
    return payload


def test_restaurant_and_category_accept_logo_upload(admin_client, restaurant):
    restaurant_response = admin_client.patch(
        f"/api/v1/restaurants/{restaurant.id}/",
        {"logo_upload": png("empresa.png")},
        format="multipart",
    )
    assert restaurant_response.status_code == 200, restaurant_response.data
    assert restaurant_response.data["logo_url"].endswith(".png")
    assert restaurant_response.data["logo_image"]

    category_response = admin_client.post(
        "/api/v1/menu/categories/",
        {"name": "Lanches", "logo_upload": png("lanches.png", "blue")},
        format="multipart",
    )
    assert category_response.status_code == 201, category_response.data
    assert category_response.data["logo_url"].endswith(".png")


def test_upload_rejects_content_that_does_not_match_extension(admin_client, restaurant):
    response = admin_client.patch(
        f"/api/v1/restaurants/{restaurant.id}/",
        {"logo_upload": disguised_jpeg()},
        format="multipart",
    )
    assert response.status_code == 400, response.data
    assert "logo_upload" in response.data["error"]["message"]


def test_product_upload_builds_primary_and_photo_list(admin_client, restaurant, branch):
    response = admin_client.post(
        "/api/v1/menu/products/",
        product_payload(
            restaurant,
            branch,
            logo_p_upload=jpeg("capa.jpg"),
            photo_uploads=[png("lado.png", "blue"), png("detalhe.png", "green")],
        ),
        format="multipart",
    )

    assert response.status_code == 201, response.data
    assert response.data["logo_p"].endswith(".jpg")
    assert len(response.data["photo_list"]) == 3
    assert sum(item["is_primary"] for item in response.data["photo_list"]) == 1
    product = Product.all_objects.get(pk=response.data["id"])
    assert ProductImage.all_objects.filter(product=product).count() == 3


def test_product_can_remove_gallery_image_and_reassign_primary(admin_client, restaurant, branch):
    created = admin_client.post(
        "/api/v1/menu/products/",
        product_payload(
            restaurant,
            branch,
            logo_p_upload=jpeg("capa.jpeg"),
            photo_uploads=[png("alternativa.png", "blue")],
        ),
        format="multipart",
    )
    primary = next(item for item in created.data["photo_list"] if item["is_primary"])
    variation = admin_client.post(
        "/api/v1/menu/variations/",
        {"product": created.data["id"], "name": "Grande", "logo_image": primary["id"]},
        format="json",
    )
    assert variation.status_code == 201, variation.data

    updated = admin_client.patch(
        f"/api/v1/menu/products/{created.data['id']}/",
        {"photo_remove_ids": [primary["id"]]},
        format="multipart",
    )

    assert updated.status_code == 200, updated.data
    assert len(updated.data["photo_list"]) == 1
    assert updated.data["photo_list"][0]["is_primary"] is True
    variation_record = ProductVariation.all_objects.get(pk=variation.data["id"])
    assert variation_record.logo_image_id is None
    variation_response = admin_client.get(f"/api/v1/menu/variations/{variation.data['id']}/")
    assert variation_response.data["logo_p"] == ""


def test_product_does_not_duplicate_same_file_in_gallery(admin_client, restaurant, branch):
    response = admin_client.post(
        "/api/v1/menu/products/",
        product_payload(
            restaurant,
            branch,
            logo_p_upload=jpeg("capa.jpg"),
            photo_uploads=[jpeg("copia.jpeg")],
        ),
        format="multipart",
    )

    assert response.status_code == 201, response.data
    assert len(response.data["photo_list"]) == 1


def test_product_patch_saves_multiple_gallery_files(admin_client, restaurant, branch):
    created = admin_client.post(
        "/api/v1/menu/products/",
        product_payload(restaurant, branch),
        format="json",
    )
    assert created.status_code == 201, created.data

    updated = admin_client.patch(
        f"/api/v1/menu/products/{created.data['id']}/",
        {"photo_uploads": [png("frente.png"), jpeg("lado.jpeg", "blue")]},
        format="multipart",
    )

    assert updated.status_code == 200, updated.data
    assert len(updated.data["photo_list"]) == 2
    assert updated.data["logo_p"]


def test_variation_only_accepts_image_from_its_product(admin_client, account, restaurant, branch):
    first = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Primeiro", internal_code="P-1", sale_price="1.00",
    )
    second = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Segundo", internal_code="P-2", sale_price="2.00",
    )
    image = Image.create_from_upload(png("segundo.png"), account=account)
    ProductImage.objects.create(account=account, product=second, image=image)

    rejected = admin_client.post(
        "/api/v1/menu/variations/",
        {"product": str(first.id), "name": "Grande", "logo_image": str(image.id)},
        format="json",
    )
    assert rejected.status_code == 400, rejected.data
    assert "logo_image" in rejected.data["error"]["message"]

    ProductImage.objects.create(account=account, product=first, image=image)
    accepted = admin_client.post(
        "/api/v1/menu/variations/",
        {"product": str(first.id), "name": "Grande", "logo_image": str(image.id)},
        format="json",
    )
    assert accepted.status_code == 201, accepted.data
    assert accepted.data["logo_p"].endswith(".png")
