import uuid
from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.test import TestCase

from chat_sync.models import ChatMessage, ChatMessageBlock, ChatThread
from chat_sync.views import _to_payload
from hospital_care.models import ChatMessageAttribution
from hospital_care.tests.factories import make_agent, make_department, make_doctor, make_hospital


class ChatSyncRegressionTests(TestCase):
    def test_hospital_attribution_does_not_change_sync_payload_shape(self):
        user = get_user_model().objects.create_user(username="chat-reg")
        hospital = make_hospital(code="REG-1")
        department = make_department(hospital)
        doctor = make_doctor(hospital, department=department)
        agent = make_agent(hospital, doctor, department)
        thread = ChatThread.objects.create(user=user, title="回归")
        message = ChatMessage.objects.create(
            user=user,
            thread=thread,
            role=ChatMessage.Role.ASSISTANT,
            client_message_id=uuid.uuid4(),
            server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
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
        ChatMessageAttribution.objects.create(
            message=message,
            actor_type=ChatMessageAttribution.ActorType.DOCTOR,
            actor_user=doctor.staff_membership.user,
            doctor=doctor,
            display_name_snapshot=doctor.display_name,
            source=ChatMessageAttribution.Source.DOCTOR_CONSOLE,
        )
        payload = _to_payload(message)
        self.assertEqual(payload["role"], "assistant")
        self.assertEqual(payload["blocks"][0]["payload"]["text"]["_0"], "同步回归")
        self.assertNotIn("actor_type", payload)
        self.assertIn("thread_id", payload)
        self.assertIn("client_message_id", payload)
