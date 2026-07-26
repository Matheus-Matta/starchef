import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import UserProfile
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.restaurants.models import Branch, Restaurant

User = get_user_model()


@pytest.mark.django_db
def test_user_lists_orders_from_own_restaurant(api_client, account, restaurant, branch, table, manager_user):
    other_branch = Branch.objects.create(account=account, restaurant=restaurant, name="Outra filial")
    other_user = User.objects.create_user("other", password="secret123")
    UserProfile.objects.create(
        account=account,
        user=other_user,
        profile_type=UserProfile.PROFILE_MANAGER,
        restaurant=restaurant,
        branch=other_branch,
    )

    own_order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_TABLE, table=table, user=manager_user)
    create_order(restaurant=restaurant, branch=other_branch, order_type=Order.TYPE_COUNTER, user=other_user)

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")
    response = api_client.get("/api/v1/orders/")

    assert response.status_code == 200
    ids = {row["id"] for row in response.data["results"]}
    assert str(own_order.id) in ids
    assert len(ids) == 2


@pytest.mark.django_db
def test_non_admin_user_only_lists_own_restaurant(api_client, account, restaurant, branch, manager_user):
    other_restaurant = Restaurant.objects.create(
        account=account,
        legal_name="Outro Restaurante LTDA",
        trade_name="Outro Restaurante",
        cnpj="00.000.000/0002-00",
    )
    Branch.objects.create(account=account, restaurant=other_restaurant, name="Outra matriz")

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")
    response = api_client.get("/api/v1/restaurants/")

    assert response.status_code == 200
    ids = {row["id"] for row in response.data["results"]}
    assert ids == {str(restaurant.id)}


@pytest.mark.django_db
def test_tenant_admin_lists_all_restaurants_from_account(api_client, account, restaurant, branch):
    other_restaurant = Restaurant.objects.create(
        account=account,
        legal_name="Outro Restaurante LTDA",
        trade_name="Outro Restaurante",
        cnpj="00.000.000/0002-00",
    )
    admin_user = User.objects.create_user("tenant-admin", password="secret123")
    UserProfile.objects.create(
        account=account,
        user=admin_user,
        profile_type=UserProfile.PROFILE_ADMIN,
        restaurant=restaurant,
        branch=branch,
    )

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(admin_user)}")
    response = api_client.get("/api/v1/restaurants/")

    assert response.status_code == 200
    ids = {row["id"] for row in response.data["results"]}
    assert {str(restaurant.id), str(other_restaurant.id)} <= ids


@pytest.mark.django_db
def test_non_admin_cannot_create_data_for_other_restaurant(api_client, account, restaurant, branch, manager_user):
    other_restaurant = Restaurant.objects.create(
        account=account,
        legal_name="Outro Restaurante LTDA",
        trade_name="Outro Restaurante",
        cnpj="00.000.000/0002-00",
    )
    other_branch = Branch.objects.create(account=account, restaurant=other_restaurant, name="Outra matriz")

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")
    response = api_client.post(
        "/api/v1/tables/sectors/",
        {
            "account": str(account.id),
            "restaurant": str(other_restaurant.id),
            "branch": str(other_branch.id),
            "name": "Salao externo",
        },
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_tenant_admin_dashboard_can_filter_or_aggregate_all_restaurants(api_client, account, restaurant, branch, manager_user):
    other_restaurant = Restaurant.objects.create(
        account=account,
        legal_name="Outro Restaurante LTDA",
        trade_name="Outro Restaurante",
        cnpj="00.000.000/0002-00",
    )
    other_branch = Branch.objects.create(account=account, restaurant=other_restaurant, name="Outra matriz")
    admin_user = User.objects.create_user("tenant-admin", password="secret123")
    UserProfile.objects.create(
        account=account,
        user=admin_user,
        profile_type=UserProfile.PROFILE_ADMIN,
        restaurant=restaurant,
        branch=branch,
    )

    create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    create_order(restaurant=other_restaurant, branch=other_branch, order_type=Order.TYPE_COUNTER, user=admin_user)

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(admin_user)}")
    all_response = api_client.get("/api/v1/reports/dashboard/")
    filtered_response = api_client.get("/api/v1/reports/dashboard/", {"restaurant": str(restaurant.id)})

    assert all_response.status_code == 200
    assert filtered_response.status_code == 200
    assert all_response.data["orders_count"] == 2
    assert filtered_response.data["orders_count"] == 1
