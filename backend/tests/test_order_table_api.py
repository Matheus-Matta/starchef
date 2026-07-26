import pytest
from rest_framework_simplejwt.tokens import AccessToken


@pytest.mark.django_db
def test_open_free_table_order_from_pdv(
    api_client, manager_user, restaurant, table
):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}"
    )

    response = api_client.post(
        "/api/v1/orders/open-table/",
        {"table": str(table.id)},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["order_type"] == "table"
    assert str(response.data["table"]) == str(table.id)


@pytest.mark.django_db
def test_open_table_returns_current_open_order(
    api_client, manager_user, table
):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}"
    )

    first = api_client.post(
        "/api/v1/orders/open-table/",
        {"table": str(table.id)},
        format="json",
    )
    second = api_client.post(
        "/api/v1/orders/open-table/",
        {"table": str(table.id)},
        format="json",
    )

    assert first.status_code == 201, first.data
    assert second.status_code == 200, second.data
    assert second.data["id"] == first.data["id"]
