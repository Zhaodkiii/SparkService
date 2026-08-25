from __future__ import annotations

import uuid

from django.conf import settings
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from chat_sync.ai_services.run_service import RunService


class ChatRunConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.groups = set()
        await self.accept()
        await self.send_json({"type": "chat.run.connected"})

    async def disconnect(self, code):
        for group in self.groups:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            await self.send_json({"type": "run.error", "code": "chat_ws_message_invalid"})
            return
        kind = content.get("type")
        if kind == "ping":
            await self.send_json({"type": "pong"})
            return
        if kind != "run.subscribe":
            await self.send_json({"type": "run.error", "code": "chat_ws_message_unsupported"})
            return
        run_id = content.get("run_id")
        try:
            run_id = str(uuid.UUID(str(run_id)))
            after = max(0, int(content.get("after_sequence") or 0))
        except (TypeError, ValueError, AttributeError):
            await self.send_json({"type": "run.error", "code": "chat_ws_subscription_invalid"})
            return
        run = await self._get_run(run_id)
        if run is None:
            await self.send_json({"type": "run.error", "code": "chat_run_not_found"})
            return
        group = f"chat_run_{run.id.hex}"
        max_subscriptions = max(1, int(getattr(settings, "CHAT_AI_WS_MAX_SUBSCRIPTIONS", 4)))
        if group not in self.groups and len(self.groups) >= max_subscriptions:
            await self.send_json({"type": "run.error", "code": "chat_ws_subscription_limit"})
            return
        await self.channel_layer.group_add(group, self.channel_name)
        self.groups.add(group)
        cursor = after
        replay_target = run.last_sequence
        while cursor < replay_target:
            events = await self._get_events(run_id, cursor)
            if not events:
                break
            for event in events:
                await self.send_json(event)
            cursor = events[-1]["sequence"]
        await self.send_json({"type": "run.subscribed", "run_id": str(run.id), "resume_after_sequence": cursor})

    async def chat_run_event(self, event):
        await self.send_json(event.get("event") or {})

    @database_sync_to_async
    def _get_run(self, run_id):
        try:
            return RunService.get_run(user_id=self.scope["user"].id, run_id=run_id)
        except Exception:
            return None

    @database_sync_to_async
    def _get_events(self, run_id, after):
        try:
            events = RunService.list_events(user_id=self.scope["user"].id, run_id=run_id, after_sequence=after, limit=200)
            return [RunService.serialize_event(event) for event in events]
        except Exception:
            return []
