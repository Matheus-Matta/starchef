"""Smoke tests do app data_exchange: export/parse de CSV respondem sem 500."""
import io

import pytest

pytestmark = pytest.mark.django_db


def test_export_csv_ok(api_client):
    payload = {
        "filename": "export.csv",
        "columns": [{"key": "name", "label": "Nome"}],
        "rows": [{"name": "Produto A"}],
    }
    resp = api_client.post("/api/v1/data-exchange/export/", payload, format="json")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")
    assert b"Nome" in resp.content


def test_parse_csv_ok(api_client):
    csv_content = "name,price\nProduto A,10.00\n".encode("utf-8-sig")
    upload = io.BytesIO(csv_content)
    upload.name = "produtos.csv"
    resp = api_client.post("/api/v1/data-exchange/parse/", {"file": upload}, format="multipart")
    assert resp.status_code == 200
    assert resp.data["count"] == 1


def test_parse_csv_without_file_is_400(api_client):
    resp = api_client.post("/api/v1/data-exchange/parse/", {}, format="multipart")
    assert resp.status_code == 400
