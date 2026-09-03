import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase

from chat_sync.models import ChatMessage, ChatThread


def _make_channel_layer():
    layer = MagicMock()
    layer.group_send = AsyncMock()
    return layer


class ChatSyncEventContractTests(TestCase):
    """CHAT-000056 16.1：v2 hint 契约——thread_id / event_id / payload_version / emitted_at。"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ws-contract")
        self.thread = ChatThread.objects.create(user=self.user, title="契约")

    def _create_message(self):
        return ChatMessage.objects.create(
            user=self.user,
            thread=self.thread,
            role=ChatMessage.Role.ASSISTANT,
            client_message_id=uuid.uuid4(),
            server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    def test_message_commit_emits_v2_event_with_thread_id(self):
        layer = _make_channel_layer()
        with patch("chat_sync.events.get_channel_layer", return_value=layer):
            with self.captureOnCommitCallbacks(execute=True):
                message = self._create_message()

        layer.group_send.assert_awaited_once()
        group, packet = layer.group_send.call_args.args
        self.assertEqual(group, f"user_{self.user.id}")
        self.assertEqual(packet["type"], "chat.sync.updated")
        event = packet["event"]
        self.assertEqual(event["type"], "chat.sync.updated")
        self.assertEqual(event["payload_version"], 2)
        self.assertEqual(event["thread_id"], str(self.thread.id))
        self.assertEqual(event["message_ids"], [message.server_message_id])
        self.assertTrue(event["event_id"])
        self.assertTrue(event["emitted_at"])
        self.assertTrue(event["cursor"])

    def test_rollback_does_not_emit_event(self):
        layer = _make_channel_layer()
        with patch("chat_sync.events.get_channel_layer", return_value=layer):
            try:
                with transaction.atomic():
                    self._create_message()
                    raise RuntimeError("force rollback")
            except RuntimeError:
                pass

        layer.group_send.assert_not_called()

    def test_legacy_call_without_thread_id_stays_v1(self):
        from chat_sync.events import ChatSyncNotifier

        layer = _make_channel_layer()
        with patch("chat_sync.events.get_channel_layer", return_value=layer):
            ChatSyncNotifier.notify_user_sync(
                user_id=self.user.id,
                cursor="2026-01-01T00:00:00+00:00",
                message_ids=[],
            )

        layer.group_send.assert_awaited_once()
        _, packet = layer.group_send.call_args.args
        event = packet["event"]
        self.assertEqual(event["payload_version"], 1)
        self.assertNotIn("thread_id", event)
        self.assertNotIn("event_id", event)
