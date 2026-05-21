import uuid
from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from chat_sync.models import ChatMessage, ChatMessageBlock, ChatThread
from chat_sync.serializers import ChatPushRequestSerializer, ChatRemoteMessageSerializer
from chat_sync.views import (
    _to_block_push_ack,
    _to_message_push_ack,
    _to_payload,
    _upsert_message_block_update,
    _upsert_message_blocks,
)


class ChatRemoteMessageSerializerBlocksOnlyTests(SimpleTestCase):
    def test_blocks_required_and_kind_content_removed(self):
        payload = {
            "thread_id": "00000000-0000-0000-0000-000000000001",
            "role": "assistant",
            "client_message_id": "00000000-0000-0000-0000-000000000002",
            "delivery_state": "sent",
            "created_at": "2026-01-01T00:00:00Z",
            "blocks": [],
        }
        serializer = ChatRemoteMessageSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("kind", serializer.validated_data)
        self.assertNotIn("content", serializer.validated_data)

    def test_reject_when_blocks_missing(self):
        payload = {
            "thread_id": "00000000-0000-0000-0000-000000000001",
            "role": "assistant",
            "client_message_id": "00000000-0000-0000-0000-000000000002",
            "delivery_state": "sent",
            "created_at": "2026-01-01T00:00:00Z",
        }
        serializer = ChatRemoteMessageSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("blocks", serializer.errors)

    def test_push_request_accepts_block_updates_without_messages(self):
        payload = {
            "block_updates": [
                {
                    "thread_id": "00000000-0000-0000-0000-000000000001",
                    "client_message_id": "00000000-0000-0000-0000-000000000002",
                    "block": {"id": "00000000-0000-0000-0000-000000000003", "kind": "taskCards"},
                }
            ]
        }
        serializer = ChatPushRequestSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["messages"], [])
        self.assertEqual(len(serializer.validated_data["block_updates"]), 1)


class ChatMessageBlockProjectionTests(TestCase):
    def test_payload_reads_blocks_from_block_table(self):
        user = get_user_model().objects.create_user(username="chat-blocks")
        thread = ChatThread.objects.create(user=user, title="Blocks")
        message = ChatMessage.objects.create(
            user=user,
            thread=thread,
            role=ChatMessage.Role.ASSISTANT,
            client_message_id=uuid.uuid4(),
            server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            metadata={"blocks": [{"id": str(uuid.uuid4()), "kind": "text", "text": "stale"}]},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        block_id = uuid.uuid4()
        ChatMessageBlock.objects.create(
            id=block_id,
            user=user,
            thread=thread,
            message=message,
            kind="text",
            status=ChatMessageBlock.Status.READY,
            revision=7,
            order_key=1000,
            node_role="timeline",
            payload={
                "id": str(block_id),
                "kind": "text",
                "text": "from block row",
                "status": "ready",
                "revision": 7,
                "node_role": "timeline",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        payload = _to_payload(message)

        self.assertEqual(len(payload["blocks"]), 1)
        self.assertEqual(payload["blocks"][0]["text"], "from block row")
        self.assertEqual(payload["blocks"][0]["node_role"], "timeline")

    def test_block_update_upserts_single_block_without_deleting_siblings(self):
        user = get_user_model().objects.create_user(username="chat-block-update")
        thread = ChatThread.objects.create(user=user, title="Blocks")
        message_id = uuid.uuid4()
        message = ChatMessage.objects.create(
            user=user,
            thread=thread,
            role=ChatMessage.Role.ASSISTANT,
            client_message_id=message_id,
            server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        text_block_id = uuid.uuid4()
        task_block_id = uuid.uuid4()
        ChatMessageBlock.objects.create(
            id=text_block_id,
            user=user,
            thread=thread,
            message=message,
            kind="text",
            status=ChatMessageBlock.Status.READY,
            revision=1,
            order_key=1000,
            node_role="timeline",
            payload={"id": str(text_block_id), "kind": "text", "text": "keep"},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        ChatMessageBlock.objects.create(
            id=task_block_id,
            user=user,
            thread=thread,
            message=message,
            kind="taskCards",
            status=ChatMessageBlock.Status.READY,
            revision=1,
            order_key=2000,
            node_role="toolPresentation",
            payload={"id": str(task_block_id), "kind": "taskCards", "revision": 1},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        _upsert_message_block_update(
            user=user,
            thread_id=thread.id,
            client_message_id=message_id,
            block={
                "id": str(task_block_id),
                "kind": "taskCards",
                "status": "ready",
                "revision": 2,
                "order_key": 2000,
                "node_role": "toolPresentation",
                "payload": {"task_cards": {"_0": []}},
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:01:00Z",
            },
        )

        self.assertTrue(ChatMessageBlock.objects.filter(id=text_block_id).exists())
        task_block = ChatMessageBlock.objects.get(id=task_block_id)
        self.assertEqual(task_block.revision, 2)
        self.assertEqual(ChatMessageBlock.objects.filter(message=message).count(), 2)

    def test_push_ack_helpers_return_metadata_without_blocks(self):
        user = get_user_model().objects.create_user(username="chat-push-ack")
        thread = ChatThread.objects.create(user=user, title="Ack")
        message = ChatMessage.objects.create(
            user=user,
            thread=thread,
            role=ChatMessage.Role.ASSISTANT,
            client_message_id=uuid.uuid4(),
            server_message_id="srv-ack-1",
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        block_id = uuid.uuid4()

        message_ack = _to_message_push_ack(message)
        self.assertEqual(message_ack["client_message_id"], str(message.client_message_id))
        self.assertEqual(message_ack["server_message_id"], "srv-ack-1")
        self.assertIn("server_updated_at", message_ack)
        self.assertNotIn("blocks", message_ack)

        block_ack = _to_block_push_ack(message, block_id)
        self.assertEqual(block_ack["client_message_id"], str(message.client_message_id))
        self.assertEqual(block_ack["block_id"], str(block_id))
        self.assertIn("server_updated_at", block_ack)
        self.assertNotIn("blocks", block_ack)
