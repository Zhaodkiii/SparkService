import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from backoffice.models import AdminAuditLog, AdminRole, AdminUserRole
from backoffice.rbac import bootstrap_admin_permissions
from chat_sync.models import ChatMessage, ChatMessageBlock, ChatThread

User = get_user_model()


class AdminConversationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.superuser = User.objects.create_user(
            username="super_admin",
            email="super@example.com",
            password="pass1234",
            is_staff=True,
            is_superuser=True,
        )
        self.staff_user = User.objects.create_user(
            username="staff_only",
            email="staff@example.com",
            password="pass1234",
            is_staff=True,
            is_superuser=False,
        )
        self.chat_user = User.objects.create_user(
            username="chat_user",
            email="chat@example.com",
            password="pass1234",
        )
        bootstrap_admin_permissions()
        super_admin = AdminRole.objects.get(code="super_admin")
        AdminUserRole.objects.create(user=self.staff_user, role=super_admin)

        now = timezone.now()
        self.thread = ChatThread.objects.create(
            user=self.chat_user,
            title="健康咨询",
            current_model_name="gpt-test",
        )
        self.deleted_thread = ChatThread.objects.create(
            user=self.chat_user,
            title="已删除会话",
            is_deleted=True,
            deleted_at=now,
        )
        self.message = ChatMessage.objects.create(
            user=self.chat_user,
            thread=self.thread,
            role=ChatMessage.Role.USER,
            client_message_id=uuid.uuid4(),
            server_message_id="srv-user-1",
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=now - timedelta(minutes=2),
        )
        self.assistant_message = ChatMessage.objects.create(
            user=self.chat_user,
            thread=self.thread,
            role=ChatMessage.Role.ASSISTANT,
            model_name="gpt-test",
            client_message_id=uuid.uuid4(),
            server_message_id="srv-assistant-1",
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=now - timedelta(minutes=1),
        )
        ChatMessageBlock.objects.create(
            user=self.chat_user,
            thread=self.thread,
            message=self.assistant_message,
            kind="text",
            status=ChatMessageBlock.Status.READY,
            revision=1780497381816121,
            order_key=900,
            payload={
                "id": str(uuid.uuid4()),
                "kind": "text",
                "payload": {
                    "deep_thought": {
                        "_0": {
                            "reasoning_content": "这是思考过程内容。",
                            "reasoning_duration_ms": 4141,
                        }
                    }
                },
            },
            created_at=now,
            updated_at=now,
        )
        ChatMessageBlock.objects.create(
            user=self.chat_user,
            thread=self.thread,
            message=self.assistant_message,
            kind="text",
            status=ChatMessageBlock.Status.READY,
            revision=1780497381778604,
            order_key=1000,
            payload={
                "id": str(uuid.uuid4()),
                "kind": "text",
                "payload": {
                    "text": {
                        "_0": "哈哈看得出来！这是助手回复正文。"
                    }
                },
            },
            created_at=now,
            updated_at=now,
        )
        self.nutrition_block = ChatMessageBlock.objects.create(
            user=self.chat_user,
            thread=self.thread,
            message=self.assistant_message,
            kind="nutritionCards",
            status=ChatMessageBlock.Status.READY,
            revision=1780497381778605,
            order_key=1100,
            payload={
                "id": str(uuid.uuid4()),
                "kind": "nutritionCards",
                "payload": {
                    "nutrition_cards": {
                        "_0": [
                            {
                                "title": "早餐",
                                "calories_kcal": 420,
                                "protein_grams": 18,
                            }
                        ]
                    }
                },
            },
            created_at=now,
            updated_at=now,
        )

    def test_conversation_users_requires_superuser(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/admin/v1/conversations/users/")
        self.assertEqual(response.status_code, 403)

    def test_conversation_users_list(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get("/api/admin/v1/conversations/users/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertGreaterEqual(data["pagination"]["total"], 1)
        self.assertGreaterEqual(data["stats"]["user_count"], 1)
        row = next(item for item in data["items"] if item["user_id"] == self.chat_user.id)
        self.assertEqual(row["user_message_count"], 1)
        self.assertEqual(row["assistant_message_count"], 1)
        self.assertEqual(row["thread_count"], 2)
        self.assertEqual(row["deleted_thread_count"], 1)

    def test_conversation_summary_threads_and_messages(self):
        self.client.force_authenticate(user=self.superuser)
        summary = self.client.get(f"/api/admin/v1/conversations/users/{self.chat_user.id}/summary/")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data["data"]["stats"]["thread_count"], 2)

        threads = self.client.get(f"/api/admin/v1/conversations/users/{self.chat_user.id}/threads/")
        self.assertEqual(threads.status_code, 200)
        self.assertEqual(threads.data["data"]["pagination"]["total"], 2)
        deleted = next(item for item in threads.data["data"]["items"] if item["is_deleted"])
        self.assertEqual(deleted["title"], "已删除会话")

        messages = self.client.get(
            f"/api/admin/v1/conversations/users/{self.chat_user.id}/threads/{self.thread.id}/messages/"
        )
        self.assertEqual(messages.status_code, 200)
        self.assertEqual(messages.data["data"]["pagination"]["total"], 2)
        assistant = next(item for item in messages.data["data"]["items"] if item["role"] == "assistant")
        self.assertEqual(len(assistant["blocks"]), 3)
        self.assertEqual(assistant["blocks"][0]["resolved_kind"], "deepThought")
        self.assertIn("思考过程", assistant["blocks"][0]["block_summary"])
        self.assertEqual(assistant["blocks"][1]["resolved_kind"], "text")
        self.assertIn("助手回复正文", assistant["blocks"][1]["block_summary"])
        nutrition = assistant["blocks"][2]
        self.assertEqual(nutrition["resolved_kind"], "nutritionCards")
        self.assertTrue(nutrition["has_heavy_detail"])
        self.assertIsNone(nutrition["payload"])
        self.assertEqual(nutrition["detail_load_mode"], "lazy")
        self.assertEqual(nutrition["detail_status"], "not_loaded")
        self.assertIn("早餐", nutrition["block_summary"])
        self.assertNotIn("raw", assistant)
        self.assertIn("debug_endpoint", assistant)

    def test_conversation_block_detail_and_debug(self):
        self.client.force_authenticate(user=self.superuser)
        messages = self.client.get(
            f"/api/admin/v1/conversations/users/{self.chat_user.id}/threads/{self.thread.id}/messages/"
        )
        assistant = next(item for item in messages.data["data"]["items"] if item["role"] == "assistant")
        nutrition = assistant["blocks"][2]

        detail = self.client.get(
            f"/api/admin/v1/conversations/users/{self.chat_user.id}/threads/{self.thread.id}/blocks/{nutrition['id']}/detail/"
        )
        self.assertEqual(detail.status_code, 200)
        detail_block = detail.data["data"]
        self.assertEqual(detail_block["detail_status"], "loaded")
        self.assertIsNotNone(detail_block["payload"])

        debug = self.client.get(
            f"/api/admin/v1/conversations/users/{self.chat_user.id}/threads/{self.thread.id}/messages/{assistant['message_db_id']}/debug/"
        )
        self.assertEqual(debug.status_code, 200)
        self.assertIn("blocks", debug.data["data"])
        self.assertTrue(AdminAuditLog.objects.filter(action="admin.conversation.block.detail").exists())
        self.assertTrue(AdminAuditLog.objects.filter(action="admin.conversation.message.debug").exists())

    def test_conversation_summary_includes_medical_stats(self):
        self.client.force_authenticate(user=self.superuser)
        summary = self.client.get(f"/api/admin/v1/conversations/users/{self.chat_user.id}/summary/")
        stats = summary.data["data"]["stats"]
        self.assertGreaterEqual(stats["medical_block_count"], 1)
        self.assertGreaterEqual(stats["heavy_block_count"], 1)

    def test_conversation_messages_reject_wrong_user_thread(self):
        other_user = User.objects.create_user(username="other", email="other@example.com", password="pass1234")
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(
            f"/api/admin/v1/conversations/users/{other_user.id}/threads/{self.thread.id}/messages/"
        )
        self.assertEqual(response.status_code, 404)

    def test_conversation_views_write_audit(self):
        self.client.force_authenticate(user=self.superuser)
        self.client.get("/api/admin/v1/conversations/users/")
        self.client.get(f"/api/admin/v1/conversations/users/{self.chat_user.id}/threads/")
        self.client.get(
            f"/api/admin/v1/conversations/users/{self.chat_user.id}/threads/{self.thread.id}/messages/"
        )
        self.assertTrue(AdminAuditLog.objects.filter(action="admin.conversation.users.list").exists())
        self.assertTrue(AdminAuditLog.objects.filter(action="admin.conversation.threads.list").exists())
        self.assertTrue(AdminAuditLog.objects.filter(action="admin.conversation.messages.list").exists())
