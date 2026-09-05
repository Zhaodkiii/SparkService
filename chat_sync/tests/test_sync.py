import uuid
from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from chat_sync.models import ChatMessage, ChatMessageBlock, ChatThread
from chat_sync.ai_models.run import ChatRun, RunStatus
from chat_sync.ai_models.event import ChatUsageRecord
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
                    "block": {
                        "id": "00000000-0000-0000-0000-000000000003",
                        "kind": "taskCards",
                        "node_role": "toolPresentation",
                        "payload": {"task_cards": {"_0": []}},
                    },
                }
            ]
        }
        serializer = ChatPushRequestSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["messages"], [])
        self.assertEqual(len(serializer.validated_data["block_updates"]), 1)


class ChatMessageBlockProjectionTests(TestCase):
    def test_projects_ios_codable_envelope_with_snake_case_discriminator(self):
        user = get_user_model().objects.create_user(username="ios-envelope")
        thread = ChatThread.objects.create(user=user, title="iOS")
        message = ChatMessage.objects.create(
            user=user, thread=thread, role=ChatMessage.Role.ASSISTANT,
            client_message_id=uuid.uuid4(), server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        block_id = uuid.uuid4()
        ChatMessageBlock.objects.create(
            id=block_id, user=user, thread=thread, message=message, kind="text",
            status=ChatMessageBlock.Status.READY, revision=1, node_role="toolPresentation",
            payload={
                "id": str(block_id),
                "node_role": "toolPresentation",
                "payload": {"search_summary": {"_0": {"query": "乳腺结节", "references": []}}},
            },
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        block = _to_payload(message)["blocks"][0]
        self.assertEqual(block["kind"], "searchSummary")
        self.assertEqual(block["node_role"], "toolPresentation")
        self.assertEqual(block["payload"]["search_summary"]["_0"]["query"], "乳腺结节")

    def test_projects_hospital_file_gallery_to_ios_file_attachments(self):
        user = get_user_model().objects.create_user(username="hospital-file-gallery")
        thread = ChatThread.objects.create(user=user, title="Hospital")
        message = ChatMessage.objects.create(
            user=user, thread=thread, role=ChatMessage.Role.USER,
            client_message_id=uuid.uuid4(), server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        ChatMessageBlock.objects.create(
            id=uuid.uuid4(), user=user, thread=thread, message=message, kind="fileGallery",
            status=ChatMessageBlock.Status.READY, revision=1, order_key=1200,
            node_role="timeline",
            payload={
                "file_gallery": {
                    "_0": [{
                        "id": "84eeb9cc-00fb-490e-9ea5-5a50ee011d5c",
                        "url": "https://cdn.example.test/consult.pdf",
                        "type": "document",
                        "order": 0,
                        "file_id": 2574,
                        "filename": "存款人密码纸.pdf",
                        "file_size": 113227,
                        "mime_type": "application/pdf",
                    }]
                }
            },
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        block = _to_payload(message)["blocks"][0]
        self.assertEqual(block["kind"], "fileAttachments")
        items = block["payload"]["file_attachments"]["_0"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "pdf")
        self.assertEqual(items[0]["file_id"], 2574)
        self.assertNotIn("file_gallery", block["payload"])

    def test_payload_reads_blocks_from_block_table(self):
        user = get_user_model().objects.create_user(username="chat-blocks")
        thread = ChatThread.objects.create(user=user, title="Blocks")
        message = ChatMessage.objects.create(
            user=user, thread=thread, role=ChatMessage.Role.ASSISTANT,
            client_message_id=uuid.uuid4(), server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            metadata={"blocks": [{"id": str(uuid.uuid4()), "kind": "text", "text": "stale"}]},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        block_id = uuid.uuid4()
        ChatMessageBlock.objects.create(
            id=block_id, user=user, thread=thread, message=message, kind="text",
            status=ChatMessageBlock.Status.READY, revision=7, order_key=1000,
            node_role="timeline",
            payload={"text": {"_0": "from block row"}},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        payload = _to_payload(message)
        self.assertEqual(len(payload["blocks"]), 1)
        self.assertEqual(payload["blocks"][0]["payload"]["text"]["_0"], "from block row")
        self.assertEqual(payload["blocks"][0]["node_role"], "timeline")
        self.assertEqual(payload["blocks"][0]["kind"], "text")

    def test_block_update_upserts_single_block_without_deleting_siblings(self):
        user = get_user_model().objects.create_user(username="chat-block-update")
        thread = ChatThread.objects.create(user=user, title="Blocks")
        message_id = uuid.uuid4()
        message = ChatMessage.objects.create(
            user=user, thread=thread, role=ChatMessage.Role.ASSISTANT,
            client_message_id=message_id, server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        text_block_id, task_block_id = uuid.uuid4(), uuid.uuid4()
        for block_id, kind, order_key, role, payload in [
            (text_block_id, "text", 1000, "timeline", {"id": str(text_block_id), "kind": "text", "text": "keep"}),
            (task_block_id, "taskCards", 2000, "toolPresentation", {"id": str(task_block_id), "kind": "taskCards", "revision": 1}),
        ]:
            ChatMessageBlock.objects.create(
                id=block_id, user=user, thread=thread, message=message, kind=kind,
                status=ChatMessageBlock.Status.READY, revision=1, order_key=order_key,
                node_role=role, payload=payload,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        _upsert_message_block_update(
            user=user, thread_id=thread.id, client_message_id=message_id,
            block={"id": str(task_block_id), "kind": "taskCards", "status": "ready", "revision": 2, "order_key": 2000, "node_role": "toolPresentation", "payload": {"task_cards": {"_0": []}}, "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:01:00Z"},
        )
        self.assertTrue(ChatMessageBlock.objects.filter(id=text_block_id).exists())
        self.assertEqual(ChatMessageBlock.objects.get(id=task_block_id).revision, 2)
        self.assertEqual(ChatMessageBlock.objects.filter(message=message).count(), 2)

    def test_push_ack_helpers_return_metadata_without_blocks(self):
        user = get_user_model().objects.create_user(username="chat-push-ack")
        thread = ChatThread.objects.create(user=user, title="Ack")
        message = ChatMessage.objects.create(
            user=user, thread=thread, role=ChatMessage.Role.ASSISTANT,
            client_message_id=uuid.uuid4(), server_message_id="srv-ack-1",
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

    def test_usage_summary_projects_tokens_model_and_tool_calls(self):
        user = get_user_model().objects.create_user(username="chat-usage")
        thread = ChatThread.objects.create(user=user, title="Usage")
        user_message = ChatMessage.objects.create(
            user=user, thread=thread, role=ChatMessage.Role.USER,
            client_message_id=uuid.uuid4(), server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assistant = ChatMessage.objects.create(
            user=user, thread=thread, role=ChatMessage.Role.ASSISTANT,
            client_message_id=uuid.uuid4(), server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        run = ChatRun.objects.create(
            user=user, thread=thread, user_message=user_message, assistant_message=assistant,
            idempotency_key="usage-1", request_hash="h",
        )
        ChatUsageRecord.objects.create(
            run=run, model="gpt", prompt_tokens=12, completion_tokens=2,
            reasoning_tokens=1, tool_calls=3,
        )
        summary = _to_payload(assistant)["usage_summary"]
        self.assertEqual(summary["model"], "gpt")
        self.assertEqual(summary["prompt_tokens"], 12)
        self.assertEqual(summary["completion_tokens"], 2)
        self.assertEqual(summary["reasoning_tokens"], 1)
        self.assertEqual(summary["tool_calls"], 3)
        self.assertIsNone(_to_payload(user_message)["usage_summary"])
        self.assertIsNone(_to_payload(user_message)["turn_summary"])

    def test_turn_summary_projects_duration_for_terminal_runs(self):
        user = get_user_model().objects.create_user(username="chat-turn-summary")
        thread = ChatThread.objects.create(user=user, title="Turn")
        user_message = ChatMessage.objects.create(
            user=user, thread=thread, role=ChatMessage.Role.USER,
            client_message_id=uuid.uuid4(), server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assistant = ChatMessage.objects.create(
            user=user, thread=thread, role=ChatMessage.Role.ASSISTANT,
            client_message_id=uuid.uuid4(), server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        started = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        finished = datetime(2026, 1, 1, 0, 0, 8, tzinfo=timezone.utc)
        run = ChatRun.objects.create(
            user=user, thread=thread, user_message=user_message, assistant_message=assistant,
            idempotency_key="turn-summary-1", request_hash="h",
            status=RunStatus.COMPLETED, started_at=started, finished_at=finished,
        )
        summary = _to_payload(assistant)["turn_summary"]
        self.assertEqual(summary["run_id"], str(run.id))
        self.assertEqual(summary["status"], RunStatus.COMPLETED)
        self.assertEqual(summary["duration_ms"], 8000)
        self.assertTrue(summary["regenerate_allowed"])
        self.assertTrue(summary["delete_allowed"])
