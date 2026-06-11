import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.orders.events import kitchen_group
from apps.restaurants.models import Branch


class KitchenConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.branch_id = self.scope["url_route"]["kwargs"]["branch_id"]
        self.sector = self.scope["url_route"]["kwargs"]["sector"]
        self.account_id = await self.get_account_id_for_branch()

        if not self.account_id:
            await self.close(code=4403)
            return

        self.group_name = kitchen_group(self.account_id, self.branch_id, self.sector)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(
            {
                "event": "connected",
                "payload": {
                    "account_id": str(self.account_id),
                    "branch_id": self.branch_id,
                    "sector": self.sector,
                },
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            data = json.loads(text_data)
            if data.get("event") == "ping":
                await self.send_json({"event": "pong", "payload": {}})

    async def kitchen_event(self, event):
        await self.send_json({"event": event["event"], "payload": event["payload"]})

    async def send_json(self, content):
        await self.send(text_data=json.dumps(content, default=str))

    @database_sync_to_async
    def get_account_id_for_branch(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            return None

        branch = Branch.all_objects.filter(pk=self.branch_id, deleted_at__isnull=True).first()
        if not branch:
            return None
        if user.is_superuser:
            return branch.account_id

        profile = getattr(user, "profile", None)
        if not profile or not profile.account_id or profile.account_id != branch.account_id:
            return None
        if str(profile.branch_id) == str(self.branch_id) or profile.profile_type in {"admin", "owner", "manager"}:
            return profile.account_id
        return None
