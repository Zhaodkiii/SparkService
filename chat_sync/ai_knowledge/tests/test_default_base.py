import threading

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from chat_sync.ai_knowledge.services import KnowledgeBaseService
from chat_sync.ai_models.knowledge import KnowledgeBase


class DefaultKnowledgeBaseServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="kbase-user")

    def test_creates_default_base_on_first_call(self):
        base = KnowledgeBaseService.get_or_create_default(self.user)
        self.assertTrue(base.is_default)
        self.assertEqual(base.kind, "personal")
        self.assertEqual(KnowledgeBase.objects.filter(user=self.user).count(), 1)

    def test_second_call_returns_same_base(self):
        first = KnowledgeBaseService.get_or_create_default(self.user)
        second = KnowledgeBaseService.get_or_create_default(self.user)
        self.assertEqual(first.id, second.id)
        self.assertEqual(KnowledgeBase.objects.filter(user=self.user).count(), 1)

    def test_different_users_get_different_default_bases(self):
        other = get_user_model().objects.create_user(username="kbase-other")
        mine = KnowledgeBaseService.get_or_create_default(self.user)
        theirs = KnowledgeBaseService.get_or_create_default(other)
        self.assertNotEqual(mine.id, theirs.id)


class DefaultKnowledgeBaseConcurrencyTests(TransactionTestCase):
    """并发请求默认知识库时，只能有一条 is_default=True 的记录落库。"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="kbase-concurrent")

    def test_concurrent_creation_only_produces_one_default_base(self):
        results: list = []
        errors: list = []

        def worker():
            try:
                results.append(KnowledgeBaseService.get_or_create_default(self.user).id)
            except Exception as exc:  # pragma: no cover - surfaced via assertion below
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(KnowledgeBase.objects.filter(user=self.user, is_default=True).count(), 1)
        self.assertEqual(len(set(results)), 1)


class DefaultKnowledgeBaseViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="kbase-view-user")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_get_default_base_returns_stable_envelope(self):
        response = self.client.get("/api/v1/ai/knowledge/default/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["code"], 0)
        data = body["data"]
        self.assertTrue(data["is_default"])
        self.assertEqual(data["kind"], "personal")

        second = self.client.get("/api/v1/ai/knowledge/default/")
        self.assertEqual(second.json()["data"]["id"], data["id"])

    def test_requires_authentication(self):
        anonymous = APIClient()
        response = anonymous.get("/api/v1/ai/knowledge/default/")
        self.assertIn(response.status_code, (401, 403))
