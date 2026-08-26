import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from chat_sync.ai_models.knowledge import KnowledgeDocument, KnowledgeMutationReceipt

PUSH_URL = "/api/v1/ai/knowledge/sync/push/"


def _create_mutation(document_id=None, title="检查报告解读", content="血脂血糖摘要", mutation_id=None):
    return {
        "mutation_id": str(mutation_id or uuid.uuid4()),
        "document_id": str(document_id or uuid.uuid4()),
        "operation": "create",
        "document": {
            "title": title,
            "content": content,
            "scope": "personal",
            "source": "user",
        },
        "client": {"platform": "ios", "version": "1.0", "device_id": "device-a"},
    }


def _update_mutation(document_id, base_revision, mutation_id=None, title="更新后的标题", content="更新后的正文"):
    return {
        "mutation_id": str(mutation_id or uuid.uuid4()),
        "document_id": str(document_id),
        "operation": "update",
        "base_revision": base_revision,
        "document": {"title": title, "content": content, "scope": "personal", "source": "user"},
    }


def _delete_mutation(document_id, base_revision, mutation_id=None):
    return {
        "mutation_id": str(mutation_id or uuid.uuid4()),
        "document_id": str(document_id),
        "operation": "delete",
        "base_revision": base_revision,
    }


class KnowledgeSyncPushTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="push-user")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.user)

    def _push(self, mutations):
        response = self.client_api.post(PUSH_URL, {"mutations": mutations}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]["results"]

    def test_create_document_is_accepted_with_revision_1(self):
        document_id = uuid.uuid4()
        results = self._push([_create_mutation(document_id=document_id)])
        self.assertEqual(len(results), 1)
        ack = results[0]
        self.assertEqual(ack["status"], "accepted")
        self.assertFalse(ack["replayed"])
        self.assertEqual(ack["revision"], 1)
        self.assertEqual(KnowledgeDocument.objects.filter(user=self.user, id=document_id).count(), 1)

    def test_replaying_same_mutation_returns_original_ack_without_new_revision(self):
        document_id = uuid.uuid4()
        mutation_id = uuid.uuid4()
        mutation = _create_mutation(document_id=document_id, mutation_id=mutation_id)

        first = self._push([mutation])[0]
        second = self._push([mutation])[0]

        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(KnowledgeDocument.objects.filter(user=self.user, id=document_id).count(), 1)
        self.assertEqual(KnowledgeMutationReceipt.objects.filter(user=self.user, mutation_id=mutation_id).count(), 1)

    def test_same_mutation_id_with_different_body_returns_idempotency_conflict(self):
        document_id = uuid.uuid4()
        mutation_id = uuid.uuid4()
        self._push([_create_mutation(document_id=document_id, mutation_id=mutation_id, title="A")])

        results = self._push(
            [_create_mutation(document_id=document_id, mutation_id=mutation_id, title="换了一个完全不同的标题")]
        )
        self.assertEqual(results[0]["status"], "error")
        self.assertEqual(results[0]["code"], "knowledge_idempotency_conflict")

    def test_duplicate_document_id_with_different_content_returns_document_id_conflict(self):
        document_id = uuid.uuid4()
        self._push([_create_mutation(document_id=document_id, title="标题一", content="内容一")])

        results = self._push([_create_mutation(document_id=document_id, title="标题二", content="内容二")])
        self.assertEqual(results[0]["status"], "error")
        self.assertEqual(results[0]["code"], "knowledge_document_id_conflict")
        self.assertIn("current_document", results[0])
        self.assertEqual(KnowledgeDocument.objects.filter(user=self.user, id=document_id).count(), 1)

    def test_update_happy_path_increments_revision(self):
        document_id = uuid.uuid4()
        self._push([_create_mutation(document_id=document_id)])

        ack = self._push([_update_mutation(document_id, base_revision=1)])[0]
        self.assertEqual(ack["status"], "accepted")
        self.assertEqual(ack["revision"], 2)
        document = KnowledgeDocument.objects.get(user=self.user, id=document_id)
        self.assertEqual(document.title, "更新后的标题")

    def test_update_with_stale_revision_returns_conflict_with_snapshot(self):
        document_id = uuid.uuid4()
        self._push([_create_mutation(document_id=document_id)])
        self._push([_update_mutation(document_id, base_revision=1)])  # revision becomes 2

        stale_ack = self._push([_update_mutation(document_id, base_revision=1, title="来自过期设备的更新")])[0]
        self.assertEqual(stale_ack["status"], "conflict")
        self.assertEqual(stale_ack["code"], "knowledge_revision_conflict")
        self.assertEqual(stale_ack["current_document"]["revision"], 2)

    def test_update_on_deleted_document_returns_document_deleted(self):
        document_id = uuid.uuid4()
        self._push([_create_mutation(document_id=document_id)])
        self._push([_delete_mutation(document_id, base_revision=1)])

        ack = self._push([_update_mutation(document_id, base_revision=1)])[0]
        self.assertEqual(ack["status"], "conflict")
        self.assertEqual(ack["code"], "knowledge_document_deleted")
        self.assertTrue(ack["current_document"]["is_deleted"])

    def test_delete_then_delete_again_is_idempotent_no_conflict(self):
        document_id = uuid.uuid4()
        self._push([_create_mutation(document_id=document_id)])
        first_delete = self._push([_delete_mutation(document_id, base_revision=1)])[0]
        second_delete = self._push([_delete_mutation(document_id, base_revision=1)])[0]

        self.assertEqual(first_delete["status"], "accepted")
        self.assertEqual(second_delete["status"], "accepted")
        self.assertTrue(second_delete["replayed"])
        document = KnowledgeDocument.objects.get(user=self.user, id=document_id)
        self.assertTrue(document.is_deleted)

    def test_batch_partial_failure_does_not_block_other_mutations(self):
        ok_document_id = uuid.uuid4()
        missing_document_id = uuid.uuid4()
        results = self._push(
            [
                _create_mutation(document_id=ok_document_id),
                _update_mutation(missing_document_id, base_revision=1),
            ]
        )
        self.assertEqual(results[0]["status"], "accepted")
        self.assertEqual(results[1]["status"], "error")
        self.assertEqual(results[1]["code"], "knowledge_document_not_found")
        self.assertEqual(KnowledgeDocument.objects.filter(user=self.user, id=ok_document_id).count(), 1)

    def test_cross_account_isolation_document_not_found_for_other_user(self):
        other = get_user_model().objects.create_user(username="push-other-user")
        other_client = APIClient()
        other_client.force_authenticate(other)

        document_id = uuid.uuid4()
        self._push([_create_mutation(document_id=document_id)])

        response = other_client.post(
            PUSH_URL, {"mutations": [_update_mutation(document_id, base_revision=1)]}, format="json"
        )
        result = response.json()["data"]["results"][0]
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["code"], "knowledge_document_not_found")

    def test_batch_larger_than_50_is_rejected(self):
        mutations = [_create_mutation() for _ in range(51)]
        response = self.client_api.post(PUSH_URL, {"mutations": mutations}, format="json")
        self.assertEqual(response.status_code, 400)
