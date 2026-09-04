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


class PdvRealtimeConsumer(RealtimeConsumer):
    """Canal do PDV Desktop, autenticado e limitado a uma unidade."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        account_id = await self.get_account_id(user)
        restaurant_id = self.scope["url_route"]["kwargs"].get("restaurant_id")
        if not account_id or not await self.can_access_restaurant(account_id, restaurant_id):
            await self.close(code=4403)
            return

        self.restaurant_id = str(restaurant_id)
        self.group_name = account_group(account_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(
            {
                "event": "connected",
                "payload": {
                    "protocol_version": 1,
                    "account_id": str(account_id),
                    "restaurant_id": self.restaurant_id,
                },
            }
        )

    async def realtime_event(self, event):
        payload = event.get("payload") or {}
        event_restaurant = str(payload.get("restaurant_id") or "")
        # Recursos da conta (sem restaurant_id, como categorias compartilhadas)
        # chegam a todas as unidades; recursos operacionais ficam na sua unidade.
        if event_restaurant and event_restaurant != self.restaurant_id:
            return
        await super().realtime_event(event)

    @database_sync_to_async
    def can_access_restaurant(self, account_id, restaurant_id):
        from apps.restaurants.models import Restaurant

        return Restaurant.all_objects.filter(
            pk=restaurant_id,
            account_id=account_id,
            deleted_at__isnull=True,
            is_active=True,
        ).exists()
