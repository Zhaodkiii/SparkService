from channels.generic.websocket import AsyncJsonWebsocketConsumer
import logging

from chat_sync.events import ChatSyncNotifier

logger = logging.getLogger("chat_sync.ws")

class ChatSyncConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or user.is_authenticated is False:
            logger.warning("chat ws connect rejected unauthenticated")
            await self.accept()
            await self.send_json({
                "type": "auth.session.invalidated",
                "msg": "unauthenticated",
            })
            await self.close(code=4401)
            return

        self.user_group = ChatSyncNotifier.user_group(user.id)
        claims = self.scope.get("auth_claims") or {}
        raw_session_id = claims.get("device_session_id")
        self.device_session_group = None
        try:
            if raw_session_id is not None and str(raw_session_id).strip():
                self.device_session_group = ChatSyncNotifier.device_session_group(int(raw_session_id))
        except (TypeError, ValueError):
            self.device_session_group = None
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        if self.device_session_group:
            await self.channel_layer.group_add(self.device_session_group, self.channel_name)
        await self.accept()
        logger.info("chat ws connected user_id=%s device_session=%s", user.id, self.device_session_group or "none")
        await self.send_json({"type": "chat.sync.connected"})

    async def disconnect(self, close_code):
        if hasattr(self, "user_group"):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        if getattr(self, "device_session_group", None):
            await self.channel_layer.group_discard(self.device_session_group, self.channel_name)
        logger.info("chat ws disconnected close_code=%s", close_code)

    async def receive_json(self, content, **kwargs):
        event_type = content.get("type")
        if event_type == "ping":
            await self.send_json({"type": "pong"})

    async def chat_sync_updated(self, event):
        await self.send_json(event.get("event") or {"type": "chat.sync.updated"})

    async def chat_device_session_invalidated(self, event):
        await self.send_json({
            "type": "auth.session.invalidated",
            "msg": event.get("reason") or "session_replaced",
        })
        await self.close(code=4401)
