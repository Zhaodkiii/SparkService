from django.test import SimpleTestCase

from chat_sync.serializers import ChatRemoteMessageSerializer


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
