from channels.generic.websocket import AsyncJsonWebsocketConsumer
import logging

from chat_sync.events import ChatSyncNotifier

logger = logging.getLogger("chat_sync.ws")

class ChatSyncConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or user.is_authenticated is False:
            logger.warning("chat ws connect rejected unauthenticated")
            await self.close(code=4401)
            return

        self.user_group = ChatSyncNotifier.user_group(user.id)
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()
        logger.info("chat ws connected user_id=%s", user.id)
        await self.send_json({"type": "chat.sync.connected"})

    async def disconnect(self, close_code):
        if hasattr(self, "user_group"):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        logger.info("chat ws disconnected close_code=%s", close_code)

    async def receive_json(self, content, **kwargs):
        event_type = content.get("type")
        if event_type == "ping":
            await self.send_json({"type": "pong"})

    async def chat_sync_updated(self, event):
        await self.send_json(event.get("event") or {"type": "chat.sync.updated"})
