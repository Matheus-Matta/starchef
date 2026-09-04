import pytest
from rest_framework_simplejwt.tokens import AccessToken


@pytest.mark.django_db
def test_direct_table_order_is_rejected(api_client, manager_user, restaurant, table):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    response = api_client.post(
        "/api/v1/orders/",
        {
            "restaurant": str(restaurant.id),
            "order_type": "table",
            "table": str(table.id),
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "order_type" in str(response.data)


@pytest.mark.django_db
def test_command_linked_to_table_creates_and_resumes_order(api_client, manager_user, table, command):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    link = api_client.post(
        f"/api/v1/commands/{command.id}/link-table/",
        {"table_id": str(table.id)},
        format="json",
    )
    first = api_client.post(
        "/api/v1/orders/open-command/",
        {"command": str(command.id)},
        format="json",
    )
    second = api_client.post(
        "/api/v1/orders/open-command/",
        {"command": str(command.id)},
        format="json",
    )

    assert link.status_code == 200, link.data
    assert first.status_code == 201, first.data
    assert second.status_code == 200, second.data
    assert second.data["id"] == first.data["id"]
    assert first.data["order_type"] == "command"
    assert str(first.data["table"]) == str(table.id)
    table.refresh_from_db()
    assert table.status == "occupied"
    assert table.current_order_id is None
