import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import UserProfile
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.restaurants.models import Branch

User = get_user_model()


@pytest.mark.django_db
def test_user_only_lists_orders_from_own_branch(api_client, account, restaurant, branch, table, manager_user):
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
    assert len(ids) == 1
