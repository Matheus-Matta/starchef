import pytest


@pytest.mark.django_db
def test_auth_login_verify_and_refresh(api_client, manager_user):
    login_response = api_client.post(
        "/api/v1/auth/login/",
        {"username": "manager", "password": "secret123"},
        format="json",
    )

    assert login_response.status_code == 200
    assert login_response.data["access"]
    assert login_response.data["refresh"]
    assert login_response.data["user"]["account_id"]
    assert login_response.data["user"]["restaurant_name"] == "StarChef"
    assert login_response.data["user"]["branch_name"] == "Matriz"

    verify_response = api_client.post(
        "/api/v1/auth/verify/",
        {"token": login_response.data["access"]},
        format="json",
    )
    assert verify_response.status_code == 200

    me_response = api_client.get(
        "/api/v1/auth/me/",
        HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}",
    )
    assert me_response.status_code == 200
    assert me_response.data["restaurant_name"] == "StarChef"
    assert me_response.data["branch_name"] == "Matriz"

    invalid_verify_response = api_client.post(
        "/api/v1/auth/verify/",
        {"token": "invalid"},
        format="json",
    )
    assert invalid_verify_response.status_code == 401

    refresh_response = api_client.post(
        "/api/v1/auth/refresh/",
        {"refresh": login_response.data["refresh"]},
        format="json",
    )
    assert refresh_response.status_code == 200
    assert refresh_response.data["access"]
