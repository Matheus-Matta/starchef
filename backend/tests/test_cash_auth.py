import pytest
from django.contrib.auth.hashers import PBKDF2PasswordHasher, make_password
from rest_framework_simplejwt.tokens import AccessToken

from apps.restaurants.models import Restaurant


@pytest.mark.django_db
def test_cash_auth_returns_only_hash_for_users_restaurant(
    api_client,
    manager_user,
    restaurant,
):
    restaurant.cash_action_password = PBKDF2PasswordHasher().encode(
        "1234",
        "StarChefOfflineTest",
        iterations=870000,
    )
    restaurant.save(update_fields=["cash_action_password", "updated_at"])
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}"
    )

    response = api_client.get(f"/api/v1/restaurants/{restaurant.id}/cash-auth/")

    assert response.status_code == 200
    assert response.data["algorithm"] == "pbkdf2_sha256"
    assert response.data["has_password"] is True
    assert response.data["password_hash"].startswith("pbkdf2_sha256$")
    assert response.data["password_hash"] != "1234"


@pytest.mark.django_db
def test_cash_auth_cannot_read_another_restaurant(
    api_client,
    manager_user,
    account,
):
    other = Restaurant.objects.create(
        account=account,
        legal_name="Outro Restaurante LTDA",
        trade_name="Outro Restaurante",
        cash_action_password=make_password("9999"),
    )
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}"
    )

    response = api_client.get(f"/api/v1/restaurants/{other.id}/cash-auth/")

    assert response.status_code == 404
