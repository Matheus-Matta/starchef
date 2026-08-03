import io

import pytest
from rest_framework_simplejwt.tokens import AccessToken


@pytest.mark.django_db
def test_csv_export_uses_only_requested_columns_and_escapes_formulas(api_client, manager_user):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")
    response = api_client.post(
        "/api/v1/data-exchange/export/",
        {
            "filename": "produtos.csv",
            "columns": [{"key": "name", "label": "Nome"}],
            "rows": [{"name": "=cmd()", "internal_secret": "hidden"}],
        },
        format="json",
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Nome" in content
    assert "'=cmd()" in content
    assert "hidden" not in content


@pytest.mark.django_db
def test_csv_parse_returns_bounded_structured_rows(api_client, manager_user):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")
    upload = io.BytesIO("Nome,Ativo\nProduto,sim\n".encode())
    upload.name = "produtos.csv"

    response = api_client.post(
        "/api/v1/data-exchange/parse/",
        {"file": upload},
        format="multipart",
    )

    assert response.status_code == 200
    assert response.data == {
        "headers": ["Nome", "Ativo"],
        "rows": [{"Nome": "Produto", "Ativo": "sim"}],
        "count": 1,
    }


@pytest.mark.django_db
def test_advanced_filter_only_uses_exposed_model_fields(api_client, manager_user, product):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    match = api_client.get("/api/v1/menu/products/?filter__name=burger")
    ignored = api_client.get("/api/v1/menu/products/?filter__password=anything")

    assert match.status_code == 200
    assert match.data["count"] == 1
    assert ignored.status_code == 200
    assert ignored.data["count"] == 1
