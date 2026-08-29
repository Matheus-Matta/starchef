"""Código de barras do produto: o que o leitor manda tem de achar UM produto.

Duas regras carregam o peso todo. Zeros à esquerda precisam sobreviver (o
código impresso na etiqueta é o código, não o número que ele representaria), e
o mesmo código não pode existir em dois produtos — senão, na frente do
cliente, o PDV teria de escolher um deles sem ter como saber qual.
"""
import uuid

import pytest

from apps.menu.barcodes import gtin_check_digit, is_valid_gtin, normalize_barcode
from apps.menu.models import Product

pytestmark = pytest.mark.django_db


def product_payload(restaurant, branch, **overrides):
    data = {
        "name": "Refrigerante lata",
        "internal_code": f"P{uuid.uuid4().hex[:6]}",
        "sale_price": "7.50",
        "restaurant": str(restaurant.id),
        "branch": str(branch.id),
    }
    data.update(overrides)
    return data


# ── a conta do dígito verificador ──────────────────────────────────────


@pytest.mark.parametrize(
    "code",
    [
        "7891000100103",  # EAN-13
        "12345670",  # EAN-8
        "036000291452",  # UPC-A
        "17891000100100",  # GTIN-14
    ],
)
def test_known_barcodes_are_valid(code):
    assert is_valid_gtin(code), code


@pytest.mark.parametrize("code", ["7891000100104", "12345671", "036000291453"])
def test_a_wrong_check_digit_is_caught(code):
    assert not is_valid_gtin(code)


def test_check_digit_matches_the_published_example():
    # Exemplo do próprio GS1 para EAN-13.
    assert gtin_check_digit("789100010010") == 3


def test_normalization_keeps_leading_zeros():
    # O que se remove é separador, nunca zero: `0000012345670` e `12345670`
    # são códigos diferentes.
    assert normalize_barcode(" 0000012345670 ") == "0000012345670"
    assert normalize_barcode("789-1000-100103") == "7891000100103"


# ── cadastro pela API ──────────────────────────────────────────────────


def test_product_accepts_a_valid_barcode(api_client, restaurant, branch):
    response = api_client.post(
        "/api/v1/menu/products/",
        product_payload(restaurant, branch, ean="789 1000 100103"),
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["ean"] == "7891000100103"


def test_leading_zeros_survive_the_round_trip(api_client, restaurant, branch):
    response = api_client.post(
        "/api/v1/menu/products/",
        product_payload(restaurant, branch, ean="00000012345670"),
        format="json",
    )

    assert response.status_code == 201, response.data
    # Guardado como texto: um campo numérico devolveria 12345670 e o leitor
    # nunca acharia este produto.
    assert response.data["ean"] == "00000012345670"


def test_a_wrong_check_digit_is_refused_at_registration(api_client, restaurant, branch):
    response = api_client.post(
        "/api/v1/menu/products/",
        product_payload(restaurant, branch, ean="7891000100104"),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "ean" in str(response.data)


def test_a_free_label_without_gtin_length_is_accepted(api_client, restaurant, branch):
    # Etiqueta interna e código de balança não são GTIN; recusar tudo que não
    # for GTIN deixaria esses produtos sem código nenhum.
    response = api_client.post(
        "/api/v1/menu/products/",
        product_payload(restaurant, branch, ean="123456"),
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["ean"] == "123456"


def test_the_same_barcode_cannot_repeat_in_the_account(api_client, restaurant, branch):
    first = api_client.post(
        "/api/v1/menu/products/",
        product_payload(restaurant, branch, ean="7891000100103"),
        format="json",
    )
    assert first.status_code == 201, first.data

    response = api_client.post(
        "/api/v1/menu/products/",
        product_payload(restaurant, branch, ean="7891000100103"),
        format="json",
    )

    assert response.status_code == 400, response.data
    message = str(response.data)
    assert "7891000100103" in message
    # A mensagem precisa dizer QUAL produto já usa o código.
    assert "Refrigerante lata" in message


def test_many_products_may_have_no_barcode(api_client, restaurant, branch):
    first = api_client.post(
        "/api/v1/menu/products/", product_payload(restaurant, branch), format="json"
    )
    second = api_client.post(
        "/api/v1/menu/products/", product_payload(restaurant, branch), format="json"
    )

    assert first.status_code == 201, first.data
    assert second.status_code == 201, second.data
    # O índice único é parcial: vazio não conflita com vazio.
    assert Product.all_objects.filter(ean="").count() == 2


def test_editing_a_product_keeps_its_own_barcode(api_client, restaurant, branch):
    created = api_client.post(
        "/api/v1/menu/products/",
        product_payload(restaurant, branch, ean="7891000100103"),
        format="json",
    )

    response = api_client.patch(
        f"/api/v1/menu/products/{created.data['id']}/",
        {"ean": "7891000100103", "name": "Refrigerante lata 350ml"},
        format="json",
    )

    assert response.status_code == 200, response.data


def test_products_can_be_searched_by_barcode(api_client, restaurant, branch):
    api_client.post(
        "/api/v1/menu/products/",
        product_payload(restaurant, branch, ean="7891000100103"),
        format="json",
    )

    response = api_client.get("/api/v1/menu/products/", {"search": "7891000100103"})

    assert response.status_code == 200, response.data
    assert [item["name"] for item in response.data["results"]] == ["Refrigerante lata"]
