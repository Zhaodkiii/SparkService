"""BACKOFFICE-CONVERSATION-000002：医生工作台实时链路服务端测试。

覆盖：ticket API（单次消费/路径绑定/权限）、事件分发（仅绑定医生、终结会话不发、
事务回滚不发、事件无正文）、Consumer 组归属与鉴权、JWT 兜底阻断。
"""

from __future__ import annotations

import hashlib
import uuid
from unittest import mock

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import path
from django.utils import timezone
from rest_framework.test import APIClient

from chat_sync.ai_models import ChatWebSocketTicket
from chat_sync.auth import JWTAuthMiddleware, resolve_auth_from_ticket_sync
from chat_sync.models import ChatMessage
from hospital_care.models import ClinicalConversationBinding, DoctorProfile, HospitalStaffMembership
from hospital_care.realtime import DOCTOR_CONVERSATION_WS_PATH
from hospital_care.realtime.dispatch import dispatch_doctor_conversation_hint
from hospital_care.realtime.doctor_conversation_consumer import DoctorConversationConsumer
from hospital_care.realtime.notifier import DoctorConversationNotifier
from hospital_care.services.conversation_service import create_patient_conversation
from hospital_care.tests.factories import (
    DummyRequest,
    make_agent,
    make_department,
    make_doctor,
    make_hospital,
    make_member,
    make_staff,
    make_user,
)

TICKET_URL = "/api/hospital/v1/doctor/conversations/ws-tickets/"
IN_MEMORY_CHANNELS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


def make_message(*, user, thread, text_server_id=None) -> ChatMessage:
    return ChatMessage.objects.create(
        user=user,
        thread=thread,
        role=ChatMessage.Role.USER,
        client_message_id=uuid.uuid4(),
        server_message_id=text_server_id or f"srv-{uuid.uuid4().hex[:16]}",
        delivery_state=ChatMessage.DeliveryState.SENT,
        created_at=timezone.now(),
    )


class DoctorConversationTicketApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.patient = make_user("rt-patient")
        self.member = make_member(self.patient)
        self.hospital = make_hospital(code="RT-H")
        self.department = make_department(self.hospital)
        self.doctor_user = make_user("rt-doc")
        self.doctor = make_doctor(self.hospital, user=self.doctor_user, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.binding = create_patient_conversation(
            request=DummyRequest(self.patient),
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
        )
        self.client.force_authenticate(self.doctor_user)

    def _create_ticket(self) -> str:
        response = self.client.post(TICKET_URL)
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data["data"]
        self.assertEqual(data["websocket_path"], DOCTOR_CONVERSATION_WS_PATH)
        self.assertGreater(data["expires_in"], 0)
        return data["ticket"]

    def test_doctor_gets_path_bound_ticket(self):
        raw = self._create_ticket()
        ticket = ChatWebSocketTicket.objects.get(token_hash=hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(ticket.user_id, self.doctor_user.id)
        self.assertEqual(ticket.websocket_path, DOCTOR_CONVERSATION_WS_PATH)
        self.assertIsNone(ticket.used_at)
        self.assertGreater(ticket.expires_at, timezone.now())

    def test_patient_user_rejected(self):
        self.client.force_authenticate(self.patient)
        response = self.client.post(TICKET_URL)
        self.assertEqual(response.status_code, 403)

    def test_hospital_admin_without_doctor_profile_rejected(self):
        admin = make_user("rt-admin")
        make_staff(self.hospital, admin, role=HospitalStaffMembership.Role.HOSPITAL_ADMIN)
        self.client.force_authenticate(admin)
        response = self.client.post(TICKET_URL)
        self.assertEqual(response.status_code, 403)

    def test_anonymous_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(TICKET_URL)
        self.assertIn(response.status_code, (401, 403))

    def test_ticket_single_use(self):
        raw = self._create_ticket()
        user, _claims = resolve_auth_from_ticket_sync(raw, DOCTOR_CONVERSATION_WS_PATH)
        self.assertTrue(user.is_authenticated)
        self.assertEqual(user.id, self.doctor_user.id)
        again, _claims = resolve_auth_from_ticket_sync(raw, DOCTOR_CONVERSATION_WS_PATH)
        self.assertFalse(again.is_authenticated)

    def test_ticket_path_binding_enforced(self):
        raw = self._create_ticket()
        user, _claims = resolve_auth_from_ticket_sync(raw, "/ws/chat/runs/")
        self.assertFalse(user.is_authenticated)
        # 路径不匹配不消费 ticket，正确路径仍可使用一次。
        user, _claims = resolve_auth_from_ticket_sync(raw, DOCTOR_CONVERSATION_WS_PATH)
        self.assertTrue(user.is_authenticated)


class DoctorConversationDispatchTests(TestCase):
    def setUp(self):
        self.patient = make_user("dp-patient")
        self.member = make_member(self.patient)
        self.hospital = make_hospital(code="DP-H")
        self.department = make_department(self.hospital)
        self.doctor_user = make_user("dp-doc")
        self.doctor = make_doctor(self.hospital, user=self.doctor_user, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.binding = create_patient_conversation(
            request=DummyRequest(self.patient),
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
        )

    def _dispatch(self, **kwargs):
        with mock.patch.object(DoctorConversationNotifier, "notify_conversation_updated") as notify:
            dispatch_doctor_conversation_hint(
                thread_id=kwargs.get("thread_id", self.binding.thread_id),
                message_id=kwargs.get("message_id", "srv-1"),
                cursor=kwargs.get("cursor", timezone.now().isoformat()),
            )
        return notify

    def test_dispatch_notifies_bound_doctor_only(self):
        notify = self._dispatch(message_id="srv-42")
        notify.assert_called_once()
        kwargs = notify.call_args.kwargs
        self.assertEqual(kwargs["doctor_id"], self.doctor.id)
        self.assertEqual(kwargs["thread_id"], self.binding.thread_id)
        self.assertEqual(kwargs["message_ids"], ["srv-42"])

    def test_dispatch_skips_ended_conversation(self):
        self.binding.service_status = ClinicalConversationBinding.ServiceStatus.ENDED
        self.binding.save(update_fields=["service_status"])
        notify = self._dispatch()
        notify.assert_not_called()

    def test_dispatch_skips_missing_binding(self):
        notify = self._dispatch(thread_id=uuid.uuid4())
        notify.assert_not_called()

    def test_dispatch_skips_inactive_doctor_profile(self):
        self.doctor.profile_status = DoctorProfile.ProfileStatus.HIDDEN
        self.doctor.save(update_fields=["profile_status"])
        notify = self._dispatch()
        notify.assert_not_called()

    def test_dispatch_skips_suspended_membership(self):
        membership = self.doctor.staff_membership
        membership.status = HospitalStaffMembership.Status.SUSPENDED
        membership.save(update_fields=["status"])
        notify = self._dispatch()
        notify.assert_not_called()


class DoctorConversationNotifierTests(TestCase):
    def test_event_contract_has_no_message_body(self):
        layer = mock.Mock()
        layer.group_send = mock.AsyncMock()
        doctor_id = uuid.uuid4()
        thread_id = uuid.uuid4()
        with mock.patch("hospital_care.realtime.notifier.get_channel_layer", return_value=layer):
            DoctorConversationNotifier.notify_conversation_updated(
                doctor_id=doctor_id,
                thread_id=thread_id,
                message_ids=["srv-7"],
                cursor="2026-09-02T22:30:00+08:00",
            )
        layer.group_send.assert_awaited_once()
        group, payload = layer.group_send.await_args.args
        self.assertEqual(group, f"hospital_doctor_{doctor_id}")
        self.assertEqual(payload["type"], "hospital.conversation.updated")
        event = payload["event"]
        self.assertEqual(event["type"], "hospital.conversation.updated")
        self.assertEqual(event["payload_version"], 1)
        self.assertEqual(event["thread_id"], str(thread_id))
        self.assertEqual(event["message_ids"], ["srv-7"])
        self.assertEqual(event["change_kind"], "message_created")
        self.assertTrue(event["event_id"])
        self.assertTrue(event["emitted_at"])
        forbidden = {"text", "blocks", "content", "patient", "member", "body"}
        self.assertTrue(forbidden.isdisjoint(event.keys()))

    def test_channel_layer_unavailable_does_not_raise(self):
        with mock.patch("hospital_care.realtime.notifier.get_channel_layer", return_value=None):
            DoctorConversationNotifier.notify_conversation_updated(
                doctor_id=uuid.uuid4(),
                thread_id=uuid.uuid4(),
                message_ids=["srv-1"],
                cursor="cursor",
            )

    def test_channel_layer_failure_does_not_raise(self):
        layer = mock.Mock()
        layer.group_send = mock.AsyncMock(side_effect=RuntimeError("channel down"))
        with mock.patch("hospital_care.realtime.notifier.get_channel_layer", return_value=layer):
            DoctorConversationNotifier.notify_conversation_updated(
                doctor_id=uuid.uuid4(),
                thread_id=uuid.uuid4(),
                message_ids=["srv-1"],
                cursor="cursor",
            )


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNELS)
class DoctorConversationSignalTests(TransactionTestCase):
    def setUp(self):
        self.patient = make_user("sg-patient")
        self.member = make_member(self.patient)
        self.hospital = make_hospital(code="SG-H")
        self.department = make_department(self.hospital)
        self.doctor_user = make_user("sg-doc")
        self.doctor = make_doctor(self.hospital, user=self.doctor_user, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.binding = create_patient_conversation(
            request=DummyRequest(self.patient),
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
        )

    def test_message_save_dispatches_after_commit(self):
        with mock.patch("hospital_care.realtime.signals.dispatch_doctor_conversation_hint") as dispatch:
            message = make_message(user=self.patient, thread=self.binding.thread)
        dispatch.assert_called_once_with(
            thread_id=self.binding.thread_id,
            message_id=message.server_message_id,
            cursor=message.server_updated_at.isoformat(),
        )

    def test_rollback_does_not_dispatch(self):
        from django.db import transaction

        with mock.patch("hospital_care.realtime.signals.dispatch_doctor_conversation_hint") as dispatch:
            try:
                with transaction.atomic():
                    make_message(user=self.patient, thread=self.binding.thread)
                    raise RuntimeError("force rollback")
            except RuntimeError:
                pass
        dispatch.assert_not_called()


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNELS)
class DoctorConversationConsumerTests(TransactionTestCase):
    def setUp(self):
        self.doctor_user = make_user("ws-doc")
        self.hospital = make_hospital(code="WS-H")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, user=self.doctor_user, department=self.department)

    def _application(self):
        return JWTAuthMiddleware(
            URLRouter([path("ws/hospital/doctor/conversations/", DoctorConversationConsumer.as_asgi())])
        )

    def _issue_ticket(self, user, websocket_path=DOCTOR_CONVERSATION_WS_PATH) -> str:
        raw = uuid.uuid4().hex + uuid.uuid4().hex
        ChatWebSocketTicket.objects.create(
            user=user,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            websocket_path=websocket_path,
            expires_at=timezone.now() + timezone.timedelta(seconds=30),
        )
        return raw

    def test_valid_ticket_connects_and_receives_event(self):
        raw = self._issue_ticket(self.doctor_user)

        async def scenario():
            communicator = WebsocketCommunicator(self._application(), f"{DOCTOR_CONVERSATION_WS_PATH}?ticket={raw}")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            hello = await communicator.receive_json_from()
            self.assertEqual(hello["type"], "hospital.conversation.connected")

            channel_layer = get_channel_layer()
            await channel_layer.group_send(
                DoctorConversationNotifier.doctor_group(self.doctor.id),
                {
                    "type": "hospital.conversation.updated",
                    "event": {
                        "type": "hospital.conversation.updated",
                        "payload_version": 1,
                        "event_id": str(uuid.uuid4()),
                        "thread_id": str(uuid.uuid4()),
                        "message_ids": ["srv-1"],
                        "cursor": "2026-09-02T22:30:00+08:00",
                        "emitted_at": "2026-09-02T22:30:00.020000+08:00",
                        "change_kind": "message_created",
                    },
                },
            )
            event = await communicator.receive_json_from()
            self.assertEqual(event["type"], "hospital.conversation.updated")
            self.assertEqual(event["message_ids"], ["srv-1"])
            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_missing_ticket_rejected(self):
        async def scenario():
            communicator = WebsocketCommunicator(self._application(), DOCTOR_CONVERSATION_WS_PATH)
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            message = await communicator.receive_json_from()
            self.assertEqual(message["type"], "auth.session.invalidated")
            close = await communicator.receive_output()
            self.assertEqual(close["type"], "websocket.close")
            self.assertEqual(close["code"], 4401)
            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_ticket_for_other_path_rejected(self):
        raw = self._issue_ticket(self.doctor_user, websocket_path="/ws/chat/runs/")

        async def scenario():
            communicator = WebsocketCommunicator(self._application(), f"{DOCTOR_CONVERSATION_WS_PATH}?ticket={raw}")
            await communicator.connect()
            message = await communicator.receive_json_from()
            self.assertEqual(message["type"], "auth.session.invalidated")
            close = await communicator.receive_output()
            self.assertEqual(close["code"], 4401)
            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_non_doctor_staff_rejected(self):
        admin = make_user("ws-admin")
        make_staff(self.hospital, admin, role=HospitalStaffMembership.Role.HOSPITAL_ADMIN)
        raw = self._issue_ticket(admin)

        async def scenario():
            communicator = WebsocketCommunicator(self._application(), f"{DOCTOR_CONVERSATION_WS_PATH}?ticket={raw}")
            await communicator.connect()
            message = await communicator.receive_json_from()
            self.assertEqual(message["type"], "auth.session.invalidated")
            self.assertEqual(message["msg"], "doctor_profile_not_active")
            close = await communicator.receive_output()
            self.assertEqual(close["code"], 4403)
            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_jwt_token_query_fallback_blocked(self):
        async def scenario():
            communicator = WebsocketCommunicator(self._application(), f"{DOCTOR_CONVERSATION_WS_PATH}?token=any-jwt")
            await communicator.connect()
            message = await communicator.receive_json_from()
            self.assertEqual(message["type"], "auth.session.invalidated")
            close = await communicator.receive_output()
            self.assertEqual(close["code"], 4401)
            await communicator.disconnect()

        async_to_sync(scenario)()
