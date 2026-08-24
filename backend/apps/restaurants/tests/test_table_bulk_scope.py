import pytest

from apps.restaurants.models import Branch, Command, Restaurant, Table, TableSector


pytestmark = pytest.mark.django_db


def _second_restaurant(account):
    restaurant = Restaurant.objects.create(
        account=account,
        legal_name="Restaurante Dois LTDA",
        trade_name="Restaurante Dois",
        cnpj="98765432000199",
    )
    return restaurant, Branch.all_objects.get(restaurant=restaurant)


def test_bulk_tables_can_repeat_1_to_20_in_different_restaurants(
    admin_client, account, restaurant, branch
):
    second_restaurant, second_branch = _second_restaurant(account)
    first_sector = TableSector.all_objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Salão principal",
    )
    # Reproduz o dado legado que causava o erro: restaurante B com a filial A.
    second_sector = TableSector.all_objects.create(
        account=account,
        restaurant=second_restaurant,
        branch=branch,
        name="Salão legado B",
    )

    first_response = admin_client.post(
        "/api/v1/tables/bulk-create/",
        {"sector": str(first_sector.id), "from_number": 1, "to_number": 20},
        format="json",
    )
    second_response = admin_client.post(
        "/api/v1/tables/bulk-create/",
        {"sector": str(second_sector.id), "from_number": 1, "to_number": 20},
        format="json",
    )

    assert first_response.status_code == 201, first_response.data
    assert second_response.status_code == 201, second_response.data
    assert first_response.data["created"] == 20
    assert second_response.data["created"] == 20
    second_sector.refresh_from_db()
    assert second_sector.branch_id == second_branch.id
    assert Table.all_objects.filter(restaurant=restaurant, number__in=[str(n) for n in range(1, 21)]).count() == 20
    assert (
        Table.all_objects.filter(
            restaurant=second_restaurant,
            number__in=[str(n) for n in range(1, 21)],
        ).count()
        == 20
    )


def test_admin_sector_uses_branch_from_selected_restaurant(admin_client, account):
    second_restaurant, second_branch = _second_restaurant(account)

    response = admin_client.post(
        "/api/v1/tables/sectors/",
        {
            "restaurant": str(second_restaurant.id),
            "name": "Área externa",
            "display_order": 1,
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    sector = TableSector.all_objects.get(pk=response.data["id"])
    assert sector.restaurant_id == second_restaurant.id
    assert sector.branch_id == second_branch.id


def test_bulk_commands_choose_next_number_per_restaurant(admin_client, account, restaurant):
    second_restaurant, _ = _second_restaurant(account)

    first_response = admin_client.post(
        "/api/v1/commands/bulk-create/",
        {"restaurant": str(restaurant.id), "from_number": 1, "to_number": 20},
        format="json",
    )
    second_response = admin_client.post(
        "/api/v1/commands/bulk-create/",
        {"restaurant": str(second_restaurant.id), "to_number": 20},
        format="json",
    )

    assert first_response.status_code == 201, first_response.data
    assert second_response.status_code == 201, second_response.data
    assert first_response.data["created"] == 20
    assert second_response.data["created"] == 20
    assert Command.all_objects.filter(restaurant=restaurant, number__range=(1, 20)).count() == 20
    assert Command.all_objects.filter(restaurant=second_restaurant, number__range=(1, 20)).count() == 20
