import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeDocument

PULL_URL = "/api/v1/ai/knowledge/sync/pull/"


def _make_base(user):
    return KnowledgeBase.objects.create(user=user, name="个人知识库", is_default=True, default_slot=1)


def _make_document(user, base, title="doc"):
    return KnowledgeDocument.objects.create(
        id=uuid.uuid4(),
        user=user,
        knowledge_base=base,
        title=title,
        content="content",
        excerpt="excerpt",
        revision=1,
        content_hash="hash",
    )


class KnowledgeSyncPullTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="pull-user")
        self.base = _make_base(self.user)
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.user)

    def test_pull_without_cursor_returns_full_snapshot(self):
        for i in range(3):
            _make_document(self.user, self.base, title=f"doc-{i}")

        response = self.client_api.get(PULL_URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(len(data["documents"]), 3)
        self.assertFalse(data["has_more"])

    def test_pull_paginates_with_cursor(self):
        for i in range(3):
            _make_document(self.user, self.base, title=f"doc-{i}")

        first_page = self.client_api.get(PULL_URL, {"limit": 2}).json()["data"]
        self.assertEqual(len(first_page["documents"]), 2)
        self.assertTrue(first_page["has_more"])

        second_page = self.client_api.get(PULL_URL, {"cursor": first_page["cursor"], "limit": 2}).json()["data"]
        self.assertEqual(len(second_page["documents"]), 1)
        self.assertFalse(second_page["has_more"])

        seen_ids = {d["id"] for d in first_page["documents"]} | {d["id"] for d in second_page["documents"]}
        self.assertEqual(len(seen_ids), 3)

    def test_pull_returns_tombstones_in_same_array(self):
        doc = _make_document(self.user, self.base)
        doc.is_deleted = True
        doc.deleted_at = timezone.now()
        doc.revision += 1
        doc.save()

        data = self.client_api.get(PULL_URL).json()["data"]
        self.assertEqual(len(data["documents"]), 1)
        self.assertTrue(data["documents"][0]["is_deleted"])

    def test_pull_isolates_documents_by_account(self):
        other = get_user_model().objects.create_user(username="pull-other")
        other_base = _make_base(other)
        _make_document(other, other_base, title="not-mine")
        _make_document(self.user, self.base, title="mine")

        data = self.client_api.get(PULL_URL).json()["data"]
        self.assertEqual(len(data["documents"]), 1)
        self.assertEqual(data["documents"][0]["title"], "mine")

    def test_pull_tie_breaker_does_not_lose_or_duplicate_rows(self):
        doc_a = _make_document(self.user, self.base, title="a")
        doc_b = _make_document(self.user, self.base, title="b")
        tied_ts = doc_a.server_updated_at
        KnowledgeDocument.objects.filter(id__in=[doc_a.id, doc_b.id]).update(server_updated_at=tied_ts)

        first_page = self.client_api.get(PULL_URL, {"limit": 1}).json()["data"]
        self.assertEqual(len(first_page["documents"]), 1)
        self.assertTrue(first_page["has_more"])

        second_page = self.client_api.get(PULL_URL, {"cursor": first_page["cursor"], "limit": 1}).json()["data"]
        self.assertEqual(len(second_page["documents"]), 1)
        self.assertFalse(second_page["has_more"])

        ids = {first_page["documents"][0]["id"], second_page["documents"][0]["id"]}
        self.assertEqual(ids, {str(doc_a.id), str(doc_b.id)})

    def test_requires_authentication(self):
        anonymous = APIClient()
        response = anonymous.get(PULL_URL)
        self.assertIn(response.status_code, (401, 403))
