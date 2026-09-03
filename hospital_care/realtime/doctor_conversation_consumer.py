from __future__ import annotations

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from hospital_care.exceptions import HospitalCareError
from hospital_care.realtime.notifier import DoctorConversationNotifier
from hospital_care.selectors.doctor_workspace import get_active_doctor

logger = logging.getLogger("hospital_care.realtime")


class DoctorConversationConsumer(AsyncJsonWebsocketConsumer):
    """BACKOFFICE-CONVERSATION-000002：医生工作台专用会话实时提示通道。

    只允许加入当前有效 DoctorProfile 对应的 `hospital_doctor_{doctor_id}` 组；
    不加入患者账号组、医院级或科室级广播组，也不接受客户端声明的医生/会话组。
    """

    async def connect(self):
        user = self.scope.get("user")
        if user is None or user.is_authenticated is False:
            logger.warning("doctor conversation ws connect rejected unauthenticated")
            await self.accept()
            await self.send_json({"type": "auth.session.invalidated", "msg": "unauthenticated"})
            await self.close(code=4401)
            return

        doctor = await self._resolve_doctor(user)
        if doctor is None:
            logger.warning("doctor conversation ws connect rejected doctor_inactive user_id=%s", user.id)
            await self.accept()
            await self.send_json({"type": "auth.session.invalidated", "msg": "doctor_profile_not_active"})
            await self.close(code=4403)
            return

        self.doctor_group = DoctorConversationNotifier.doctor_group(doctor.id)
        await self.channel_layer.group_add(self.doctor_group, self.channel_name)
        await self.accept()
        logger.info("doctor conversation ws connected doctor_id=%s", doctor.id)
        await self.send_json({"type": "hospital.conversation.connected"})

    async def disconnect(self, close_code):
        group = getattr(self, "doctor_group", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)
        logger.info("doctor conversation ws disconnected close_code=%s", close_code)

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    async def hospital_conversation_updated(self, event):
        await self.send_json(event.get("event") or {"type": "hospital.conversation.updated"})

    @database_sync_to_async
    def _resolve_doctor(self, user):
        try:
            return get_active_doctor(user=user)
        except HospitalCareError:
            return None
