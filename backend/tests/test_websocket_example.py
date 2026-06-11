import pytest
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from config.asgi import application


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_kitchen_websocket_connects_with_jwt(branch, manager_user):
    token = AccessToken.for_user(manager_user)
    communicator = WebsocketCommunicator(application, f"/ws/kitchen/{branch.id}/kitchen/?token={token}")
    connected, _ = await communicator.connect()

    assert connected is True

    await communicator.send_json_to({"event": "ping"})
    response = await communicator.receive_json_from()
    assert response["event"] in {"connected", "pong"}

    await communicator.disconnect()

