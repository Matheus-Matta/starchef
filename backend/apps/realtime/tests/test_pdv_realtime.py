import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Account
from apps.realtime.events import account_group
from apps.restaurants.models import Restaurant
from config.asgi import application


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_pdv_websocket_requires_jwt(restaurant):
    communicator = WebsocketCommunicator(application, f"/ws/pdv/{restaurant.id}/")

    connected, close_code = await communicator.connect()

    assert connected is False
    assert close_code == 4401


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_pdv_websocket_accepts_bearer_jwt_and_identifies_restaurant(
    account, restaurant, manager_user
):
    token = AccessToken.for_user(manager_user)
    communicator = WebsocketCommunicator(
        application,
        f"/ws/pdv/{restaurant.id}/",
        headers=[(b"authorization", f"Bearer {token}".encode())],
    )

    connected, _ = await communicator.connect()
    assert connected is True

    message = await communicator.receive_json_from()
    assert message == {
        "event": "connected",
        "payload": {
            "protocol_version": 1,
            "account_id": str(account.id),
            "restaurant_id": str(restaurant.id),
        },
    }

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_pdv_websocket_rejects_restaurant_from_another_account(manager_user):
    @database_sync_to_async
    def create_other_restaurant():
        account = Account.objects.create(
            name="Outra conta",
            slug="outra-conta-ws",
            status=Account.STATUS_ACTIVE,
            is_active=True,
        )
        return Restaurant.objects.create(
            account=account,
            legal_name="Outro Restaurante LTDA",
            trade_name="Outro Restaurante",
            cnpj="12345678000199",
        )

    other_restaurant = await create_other_restaurant()
    token = AccessToken.for_user(manager_user)
    communicator = WebsocketCommunicator(
        application,
        f"/ws/pdv/{other_restaurant.id}/",
        headers=[(b"authorization", f"Bearer {token}".encode())],
    )

    connected, close_code = await communicator.connect()

    assert connected is False
    assert close_code == 4403


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_pdv_websocket_filters_events_from_another_restaurant(
    account, restaurant, manager_user
):
    token = AccessToken.for_user(manager_user)
    communicator = WebsocketCommunicator(
        application,
        f"/ws/pdv/{restaurant.id}/",
        headers=[(b"authorization", f"Bearer {token}".encode())],
    )
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.receive_json_from()  # connected

    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        account_group(account.id),
        {
            "type": "realtime.event",
            "event": "model.updated",
            "payload": {
                "resource": "orders.order",
                "restaurant_id": "00000000-0000-0000-0000-000000000001",
            },
        },
    )
    assert await communicator.receive_nothing(timeout=0.1)

    await channel_layer.group_send(
        account_group(account.id),
        {
            "type": "realtime.event",
            "event": "model.updated",
            "payload": {
                "resource": "orders.orderitem",
                "restaurant_id": str(restaurant.id),
                "id": "item-1",
            },
        },
    )
    message = await communicator.receive_json_from()
    assert message["event"] == "model.updated"
    assert message["payload"]["resource"] == "orders.orderitem"

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tenant_model_update_is_pushed_to_pdv(restaurant, manager_user):
    token = AccessToken.for_user(manager_user)
    communicator = WebsocketCommunicator(
        application,
        f"/ws/pdv/{restaurant.id}/",
        headers=[(b"authorization", f"Bearer {token}".encode())],
    )
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.receive_json_from()  # connected

    @database_sync_to_async
    def rename_restaurant():
        restaurant.trade_name = "Restaurante atualizado"
        restaurant.save(update_fields=["trade_name", "updated_at"])

    await rename_restaurant()
    message = await communicator.receive_json_from()

    assert message["event"] == "model.updated"
    assert message["payload"]["resource"] == "restaurants.restaurant"
    assert message["payload"]["id"] == str(restaurant.id)
    assert message["payload"]["changed_fields"] == ["trade_name", "updated_at"]
    assert message["payload"]["protocol_version"] == 1

    await communicator.disconnect()
