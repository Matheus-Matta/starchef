import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.notifications.events import notification_group


class NotificationConsumer(AsyncWebsocketConsumer):
    """WebSocket por usuário: entrega notificações em tempo real.

    Autenticação via JWT no query string (JwtAuthMiddleware). Cada usuário entra
    no seu próprio grupo `notif_u<id>`.
    """

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4403)
            return

        self.user = user
        self.group_name = notification_group(user.pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"event": "connected", "payload": {"unread": await self.unread_count()}})

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            data = json.loads(text_data)
            if data.get("event") == "ping":
                await self.send_json({"event": "pong", "payload": {}})

    async def notification_message(self, event):
        await self.send_json({"event": "notification", "payload": event["payload"]})

    async def send_json(self, content):
        await self.send(text_data=json.dumps(content, default=str))

    @database_sync_to_async
    def unread_count(self):
        from apps.notifications.models import Notification

        return Notification.all_objects.filter(recipient=self.user, is_read=False, deleted_at__isnull=True).count()
