import uuid
from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.test import TestCase

from chat_sync.models import ChatMessage, ChatMessageBlock, ChatThread
from chat_sync.views import _to_payload
from hospital_care.models import ChatMessageAttribution
from hospital_care.tests.factories import make_agent, make_department, make_doctor, make_hospital


def _make_message(user, thread, role=ChatMessage.Role.ASSISTANT, model_name=None):
    kwargs = {}
    if model_name is not None:
        kwargs["model_name"] = model_name
    message = ChatMessage.objects.create(
        user=user,
        thread=thread,
        role=role,
        client_message_id=uuid.uuid4(),
        server_message_id=str(uuid.uuid4()),
        delivery_state=ChatMessage.DeliveryState.SENT,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        **kwargs,
    )
    ChatMessageBlock.objects.create(
        id=uuid.uuid4(),
        user=user,
        thread=thread,
        message=message,
        kind="text",
        status=ChatMessageBlock.Status.READY,
        revision=1,
        order_key=1000,
        node_role="timeline",
        payload={"text": {"_0": "同步回归"}},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    return message


class ChatSyncSenderProjectionTests(TestCase):
    """CHAT-000056 15.3：同步 payload 投影可选 sender；普通消息不受影响。"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="chat-reg")
        self.hospital = make_hospital(code="REG-1")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.thread = ChatThread.objects.create(user=self.user, title="回归")

    def test_doctor_attribution_projects_sender_snapshot(self):
        message = _make_message(self.user, self.thread)
        ChatMessageAttribution.objects.create(
            message=message,
            actor_type=ChatMessageAttribution.ActorType.DOCTOR,
            actor_user=self.doctor.staff_membership.user,
            doctor=self.doctor,
            display_name_snapshot=self.doctor.display_name,
            source=ChatMessageAttribution.Source.DOCTOR_CONSOLE,
        )

        payload = _to_payload(message)

        self.assertEqual(payload["role"], "assistant")
        self.assertEqual(payload["blocks"][0]["payload"]["text"]["_0"], "同步回归")
        self.assertIn("thread_id", payload)
        self.assertIn("client_message_id", payload)
        sender = payload["sender"]
        self.assertIsNotNone(sender)
        self.assertEqual(sender["actor_type"], "doctor")
        self.assertEqual(sender["actor_id"], str(self.doctor.staff_membership.user_id))
        self.assertEqual(sender["display_name"], self.doctor.display_name)
        self.assertEqual(sender["title"], self.doctor.title)
        self.assertEqual(sender["source"], "doctor_console")

    def test_ai_agent_attribution_projects_ai_sender_not_doctor(self):
        message = _make_message(self.user, self.thread, model_name="demo-model")
        ChatMessageAttribution.objects.create(
            message=message,
            actor_type=ChatMessageAttribution.ActorType.AI_AGENT,
            agent=self.agent,
            display_name_snapshot=self.agent.name,
            source=ChatMessageAttribution.Source.AI_RUNTIME,
        )

        payload = _to_payload(message)

        sender = payload["sender"]
        self.assertIsNotNone(sender)
        self.assertEqual(sender["actor_type"], "ai_agent")
        self.assertEqual(sender["actor_id"], str(self.agent.id))
        self.assertEqual(sender["display_name"], self.agent.name)
        self.assertEqual(sender["department_name"], self.department.name)
        self.assertIsNone(sender["title"])

    def test_plain_message_without_attribution_keeps_sender_none(self):
        message = _make_message(self.user, self.thread, role=ChatMessage.Role.USER)

        payload = _to_payload(message)

        # 普通历史消息：payload 原字段保持可用，sender 为空且不得被推断为真人医生。
        self.assertIsNone(payload["sender"])
        self.assertEqual(payload["role"], "user")
        self.assertEqual(payload["blocks"][0]["payload"]["text"]["_0"], "同步回归")
        self.assertIn("thread_id", payload)
