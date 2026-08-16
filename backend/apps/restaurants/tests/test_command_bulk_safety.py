import pytest

from apps.restaurants.models import Command


pytestmark = pytest.mark.django_db


def _command(account, restaurant, branch, number, **extra):
    return Command.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        number=number,
        **extra,
    )


def test_bulk_delete_uses_one_request_and_soft_deletes_free_commands(
    admin_client, account, restaurant, branch
):
    commands = [_command(account, restaurant, branch, number) for number in range(100, 105)]

    response = admin_client.post(
        "/api/v1/commands/bulk-delete/",
        {"ids": [str(command.id) for command in commands]},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data == {"deleted": 5}
    assert Command.all_objects.filter(id__in=[command.id for command in commands], deleted_at__isnull=False).count() == 5


def test_bulk_delete_is_atomic_when_one_command_is_occupied(
    admin_client, account, restaurant, branch
):
    free = _command(account, restaurant, branch, 200)
    occupied = _command(account, restaurant, branch, 201, status=Command.STATUS_OCCUPIED)

    response = admin_client.post(
        "/api/v1/commands/bulk-delete/",
        {"ids": [str(free.id), str(occupied.id)]},
        format="json",
    )

    assert response.status_code == 400, response.data
    assert Command.all_objects.filter(id__in=[free.id, occupied.id], deleted_at__isnull=True).count() == 2


def test_bulk_create_rejects_more_than_safety_limit(admin_client, restaurant):
    response = admin_client.post(
        "/api/v1/commands/bulk-create/",
        {"restaurant": str(restaurant.id), "from_number": 1, "to_number": 201},
        format="json",
    )

    assert response.status_code == 400, response.data


def test_bulk_update_changes_all_commands_with_one_request(
    admin_client, account, restaurant, branch
):
    commands = [_command(account, restaurant, branch, number) for number in range(300, 305)]

    response = admin_client.post(
        "/api/v1/commands/bulk-update/",
        {
            "ids": [str(command.id) for command in commands],
            "changes": {"is_active": False},
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data == {"updated": 5}
    assert Command.all_objects.filter(id__in=[command.id for command in commands], is_active=False).count() == 5


def test_bulk_update_rejects_fields_outside_allowlist(
    admin_client, account, restaurant, branch
):
    command = _command(account, restaurant, branch, 400)
    response = admin_client.post(
        "/api/v1/commands/bulk-update/",
        {"ids": [str(command.id)], "changes": {"status": Command.STATUS_OCCUPIED}},
        format="json",
    )

    assert response.status_code == 400, response.data
