import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .events import account_group


class RealtimeConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        account_id = await self.get_account_id(user)
        if not account_id:
            await self.close(code=4403)
            return

        self.group_name = account_group(account_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"event": "connected", "payload": {"account_id": str(account_id)}})

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except ValueError:
            return
        if data.get("event") == "ping":
            await self.send_json({"event": "pong", "payload": {}})

    async def realtime_event(self, event):
        await self.send_json({"event": event["event"], "payload": event["payload"]})

    async def send_json(self, content):
        await self.send(text_data=json.dumps(content, default=str))

    @database_sync_to_async
    def get_account_id(self, user):
        profile = getattr(user, "profile", None)
        return getattr(profile, "account_id", None) or getattr(user, "account_id", None)
