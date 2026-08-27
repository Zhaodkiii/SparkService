import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeDocument


class KnowledgeBasesApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="kb-api-user")
        self.other = get_user_model().objects.create_user(username="kb-api-other")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.user)

    def test_list_empty_is_200(self):
        response = self.client_api.get("/api/v1/ai/knowledge/bases/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["items"], [])
        self.assertIsNone(response.json()["data"]["next_cursor"])

    def test_create_and_get_detail(self):
        response = self.client_api.post(
            "/api/v1/ai/knowledge/bases/",
            {"name": "糖尿病随访资料", "kind": "personal"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()["data"]
        self.assertEqual(data["name"], "糖尿病随访资料")
        self.assertIn("permissions", data)
        self.assertFalse(data["is_default"])
        detail = self.client_api.get(f"/api/v1/ai/knowledge/bases/{data['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["data"]["id"], data["id"])

    def test_create_is_idempotent(self):
        key = str(uuid.uuid4())
        first = self.client_api.post("/api/v1/ai/knowledge/bases/", {"name": "A"}, format="json", HTTP_IDEMPOTENCY_KEY=key)
        second = self.client_api.post("/api/v1/ai/knowledge/bases/", {"name": "A"}, format="json", HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(first.json()["data"]["id"], second.json()["data"]["id"])
        self.assertEqual(KnowledgeBase.objects.filter(user=self.user).count(), 1)

    def test_revision_conflict(self):
        created = self.client_api.post("/api/v1/ai/knowledge/bases/", {"name": "B"}, format="json")
        base_id = created.json()["data"]["id"]
        conflict = self.client_api.patch(
            f"/api/v1/ai/knowledge/bases/{base_id}/",
            {"name": "B2"},
            format="json",
            HTTP_IF_MATCH='"99"',
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["data"]["error_code"], "knowledge_base_revision_conflict")

    def test_cannot_delete_default_base(self):
        default = self.client_api.get("/api/v1/ai/knowledge/default/")
        base_id = default.json()["data"]["id"]
        response = self.client_api.delete(f"/api/v1/ai/knowledge/bases/{base_id}/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["data"]["error_code"], "knowledge_base_default_undeletable")

    def test_other_user_base_is_not_found(self):
        other_client = APIClient()
        other_client.force_authenticate(self.other)
        created = other_client.post("/api/v1/ai/knowledge/bases/", {"name": "secret"}, format="json")
        base_id = created.json()["data"]["id"]
        response = self.client_api.get(f"/api/v1/ai/knowledge/bases/{base_id}/")
        self.assertEqual(response.status_code, 404)

    def test_document_crud(self):
        created = self.client_api.post("/api/v1/ai/knowledge/bases/", {"name": "docs"}, format="json")
        base_id = created.json()["data"]["id"]
        posted = self.client_api.post(
            f"/api/v1/ai/knowledge/bases/{base_id}/documents/",
            {"title": "空腹血糖随访规范", "content": "内容摘要"},
            format="json",
        )
        self.assertEqual(posted.status_code, 201, posted.content)
        document_id = posted.json()["data"]["id"]
        listed = self.client_api.get(f"/api/v1/ai/knowledge/bases/{base_id}/documents/")
        self.assertEqual(len(listed.json()["data"]["items"]), 1)
        self.assertNotIn("content", listed.json()["data"]["items"][0])
        detail = self.client_api.get(f"/api/v1/ai/knowledge/documents/{document_id}/")
        self.assertEqual(detail.json()["data"]["content"], "内容摘要")
        revision = posted.json()["data"]["revision"]
        updated = self.client_api.patch(
            f"/api/v1/ai/knowledge/documents/{document_id}/",
            {"title": "新标题", "content": "新内容"},
            format="json",
            HTTP_IF_MATCH=f'"{revision}"',
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(KnowledgeDocument.objects.get(id=document_id).title, "新标题")
        deleted = self.client_api.delete(f"/api/v1/ai/knowledge/documents/{document_id}/")
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(KnowledgeDocument.objects.get(id=document_id).is_deleted)

    def test_unauthenticated_rejected(self):
        anonymous = APIClient()
        response = anonymous.get("/api/v1/ai/knowledge/bases/")
        self.assertIn(response.status_code, (401, 403))
