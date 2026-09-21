from django.conf import settings


def test_cors_preflight_allows_restaurant_header(client):
    """Selecionar uma unidade na sidebar não pode ser bloqueado pelo navegador."""
    origin = settings.CORS_ALLOWED_ORIGINS[0]

    response = client.options(
        "/api/v1/commands/",
        HTTP_ORIGIN=origin,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-restaurant-id",
    )

    allowed_headers = response.headers["Access-Control-Allow-Headers"].lower().split(", ")
    assert response.status_code == 200
    assert "x-restaurant-id" in allowed_headers
