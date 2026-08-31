import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from chat_sync.ai_models.memory import AIMemory, AIMemoryMutationReceipt

PUSH_URL = "/api/v1/ai/memory/sync/push/"
PULL_URL = "/api/v1/ai/memory/sync/pull/"
ENTRIES_URL = "/api/v1/ai/memory/entries/"


def _create_mutation(memory_id=None, content="回答默认使用中文。", mutation_id=None, **overrides):
    payload = {
        "mutation_id": str(mutation_id or uuid.uuid4()),
        "memory_id": str(memory_id or uuid.uuid4()),
        "operation": "create",
        "memory": {
            "scope": "account",
            "layer": "L3",
            "document_key": "preferences",
            "section_key": "answer_style",
            "memory_type": "preference",
            "title": "回答语言",
            "content": content,
            "source": "user",
            "sensitivity": "normal",
        },
        "client": {"platform": "ios", "version": "1.0", "device_id": "device-a"},
    }
    payload.update(overrides)
    return payload


class MemorySyncPushTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="mem-push")
        self.other = get_user_model().objects.create_user(username="mem-push-other")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.user)

    def _push(self, mutations):
        response = self.client_api.post(PUSH_URL, {"mutations": mutations}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]["results"]

    def test_create_is_accepted_with_revision_1(self):
        memory_id = uuid.uuid4()
        ack = self._push([_create_mutation(memory_id=memory_id)])[0]
        self.assertEqual(ack["status"], "accepted")
        self.assertFalse(ack["replayed"])
        self.assertEqual(ack["revision"], 1)
        self.assertEqual(AIMemory.objects.filter(user=self.user, id=memory_id).count(), 1)

    def test_replay_same_mutation_does_not_create_second_row(self):
        memory_id = uuid.uuid4()
        mutation_id = uuid.uuid4()
        mutation = _create_mutation(memory_id=memory_id, mutation_id=mutation_id)
        first = self._push([mutation])[0]
        second = self._push([mutation])[0]
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(AIMemory.objects.filter(user=self.user, id=memory_id).count(), 1)
        self.assertEqual(AIMemoryMutationReceipt.objects.filter(user=self.user, mutation_id=mutation_id).count(), 1)

    def test_same_mutation_id_different_body_returns_reused_error(self):
        memory_id = uuid.uuid4()
        mutation_id = uuid.uuid4()
        self._push([_create_mutation(memory_id=memory_id, mutation_id=mutation_id, content="回答用中文。")])
        ack = self._push([_create_mutation(memory_id=memory_id, mutation_id=mutation_id, content="回答请尽量简短。")])[0]
        self.assertEqual(ack["status"], "error")
        self.assertEqual(ack["reason_code"], "memory_mutation_reused")

    def test_duplicate_normalized_key_returns_existing_snapshot(self):
        first_id = uuid.uuid4()
        second_id = uuid.uuid4()
        self._push([_create_mutation(memory_id=first_id, content="回答默认使用中文。")])
        ack = self._push([_create_mutation(memory_id=second_id, content="回答默认使用中文。")])[0]
        self.assertEqual(ack["status"], "conflict")
        self.assertEqual(ack["reason_code"], "duplicate_memory_key")
        self.assertEqual(ack["memory_id"], str(first_id))
        self.assertEqual(AIMemory.objects.filter(user=self.user, is_deleted=False).count(), 1)

    def test_update_mutation_is_accepted(self):
        memory_id = uuid.uuid4()
        created = self._push([_create_mutation(memory_id=memory_id)])[0]
        ack = self._push(
            [
                {
                    "mutation_id": str(uuid.uuid4()),
                    "memory_id": str(memory_id),
                    "operation": "update",
                    "base_revision": created["revision"],
                    "memory": {"content": "回答尽量简短。", "scope": "account", "layer": "L3", "document_key": "preferences"},
                }
            ]
        )[0]
        self.assertEqual(ack["status"], "accepted")
        self.assertEqual(ack["revision"], 2)
        memory = AIMemory.objects.get(user=self.user, id=memory_id)
        self.assertEqual(memory.revision, 2)
        self.assertEqual(memory.content, "回答尽量简短。")

    def test_stale_update_returns_revision_conflict(self):
        memory_id = uuid.uuid4()
        self._push([_create_mutation(memory_id=memory_id)])
        ack = self._push(
            [
                {
                    "mutation_id": str(uuid.uuid4()),
                    "memory_id": str(memory_id),
                    "operation": "update",
                    "base_revision": 0,
                    "memory": {"content": "过期版本。", "scope": "account", "layer": "L3", "document_key": "preferences"},
                }
            ]
        )[0]
        self.assertEqual(ack["status"], "conflict")
        self.assertEqual(ack["reason_code"], "revision_conflict")
        self.assertEqual(ack["resolution"], "server_wins")
        memory = AIMemory.objects.get(user=self.user, id=memory_id)
        self.assertEqual(memory.revision, 1)
        self.assertEqual(memory.content, "回答默认使用中文。")

    def test_delete_mutation_is_accepted(self):
        memory_id = uuid.uuid4()
        created = self._push([_create_mutation(memory_id=memory_id)])[0]
        ack = self._push(
            [
                {
                    "mutation_id": str(uuid.uuid4()),
                    "memory_id": str(memory_id),
                    "operation": "delete",
                    "base_revision": created["revision"],
                }
            ]
        )[0]
        self.assertEqual(ack["status"], "accepted")
        self.assertEqual(AIMemory.objects.filter(user=self.user, id=memory_id, is_deleted=False).count(), 0)
        tomb = AIMemory.objects.get(user=self.user, id=memory_id)
        self.assertTrue(tomb.is_deleted)
        self.assertEqual(tomb.revision, 2)

    def test_batch_isolates_stale_update(self):
        good_id = uuid.uuid4()
        existing_id = uuid.uuid4()
        self._push([_create_mutation(memory_id=existing_id)])
        results = self._push(
            [
                _create_mutation(memory_id=good_id, content="称呼我为小华。"),
                {
                    "mutation_id": str(uuid.uuid4()),
                    "memory_id": str(existing_id),
                    "operation": "update",
                    "base_revision": 0,
                    "memory": {"content": "冲突内容。", "scope": "account", "layer": "L3", "document_key": "preferences"},
                },
            ]
        )
        by_id = {item["memory_id"]: item for item in results}
        self.assertEqual(by_id[str(good_id)]["status"], "accepted")
        self.assertEqual(by_id[str(existing_id)]["status"], "conflict")
        self.assertEqual(by_id[str(existing_id)]["reason_code"], "revision_conflict")

    def test_account_isolation(self):
        memory_id = uuid.uuid4()
        self._push([_create_mutation(memory_id=memory_id)])
        other_client = APIClient()
        other_client.force_authenticate(self.other)
        data = other_client.get(PULL_URL).json()["data"]
        self.assertEqual(data["items"], [])
        listed = other_client.get(ENTRIES_URL).json()["data"]["items"]
        self.assertEqual(listed, [])
        self.assertEqual(AIMemory.objects.filter(user=self.other).count(), 0)

    def test_agent_scope_create_is_rejected(self):
        ack = self._push(
            [
                _create_mutation(
                    memory={
                        "scope": "agent",
                        "agent_key": "assistant",
                        "layer": "L3",
                        "document_key": "preferences",
                        "content": "只对这个 agent 生效。",
                    }
                )
            ]
        )[0]
        self.assertEqual(ack["status"], "error")
        self.assertEqual(ack["reason_code"], "memory_payload_invalid")
        self.assertEqual(AIMemory.objects.filter(user=self.user).count(), 0)


class MemorySyncPullTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="mem-pull")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.user)

    def test_pull_returns_tombstones_and_paginates(self):
        ids = []
        for i in range(3):
            memory = AIMemory.objects.create(
                id=uuid.uuid4(),
                user=self.user,
                scope="account",
                scope_key="account",
                layer="L3",
                document_key="preferences",
                section_key="answer_style",
                memory_type="preference",
                normalized_key=f"preference.{i}",
                dedup_key=f"{'a' * 63}{i}",
                title=f"t{i}",
                content=f"content {i}",
                content_hash=f"hash{i}",
                revision=1,
            )
            ids.append(memory.id)
        tomb = AIMemory.objects.get(id=ids[0])
        tomb.is_deleted = True
        tomb.deleted_at = timezone.now()
        tomb.dedup_key = None
        tomb.revision = 2
        tomb.save()

        first = self.client_api.get(PULL_URL, {"limit": 2}).json()["data"]
        self.assertEqual(len(first["items"]), 2)
        self.assertTrue(first["has_more"])
        second = self.client_api.get(PULL_URL, {"cursor": first["next_cursor"], "limit": 2}).json()["data"]
        self.assertEqual(len(second["items"]), 1)
        self.assertFalse(second["has_more"])
        all_ids = {item["id"] for item in first["items"] + second["items"]}
        self.assertEqual(len(all_ids), 3)
        self.assertTrue(any(item["is_deleted"] for item in first["items"] + second["items"]))
        self.assertTrue(str(first["next_cursor"]).startswith("m1:"))


class MemoryEntryAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="mem-entry")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.user)

    def test_manual_create_list_and_read(self):
        created = self.client_api.post(ENTRIES_URL, {"content": "解释时先给结论。"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        memory_id = created.json()["data"]["id"]
        listed = self.client_api.get(ENTRIES_URL)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(len(listed.json()["data"]["items"]), 1)
        detail = self.client_api.get(f"{ENTRIES_URL}{memory_id}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["data"]["content"], "解释时先给结论。")

    def test_patch_and_delete_with_revision(self):
        created = self.client_api.post(ENTRIES_URL, {"content": "解释时先给结论。"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        memory_id = created.json()["data"]["id"]
        revision = created.json()["data"]["revision"]
        patched = self.client_api.patch(
            f"{ENTRIES_URL}{memory_id}/",
            {"content": "解释时先给结论，再给依据。", "revision": revision},
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertEqual(patched.json()["data"]["content"], "解释时先给结论，再给依据。")
        next_revision = patched.json()["data"]["revision"]
        deleted = self.client_api.delete(f"{ENTRIES_URL}{memory_id}/?revision={next_revision}")
        self.assertEqual(deleted.status_code, 200, deleted.content)
        self.assertEqual(AIMemory.objects.filter(user=self.user, id=memory_id, is_deleted=False).count(), 0)

    def test_patch_without_revision_is_rejected(self):
        created = self.client_api.post(ENTRIES_URL, {"content": "解释时先给结论。"}, format="json")
        memory_id = created.json()["data"]["id"]
        patched = self.client_api.patch(
            f"{ENTRIES_URL}{memory_id}/",
            {"content": "解释时先给结论，再给依据。"},
            format="json",
        )
        self.assertEqual(patched.status_code, 428)

    def test_other_account_cannot_read_entry(self):
        created = self.client_api.post(ENTRIES_URL, {"content": "解释时先给结论。"}, format="json")
        memory_id = created.json()["data"]["id"]
        other = get_user_model().objects.create_user(username="mem-entry-other")
        other_client = APIClient()
        other_client.force_authenticate(other)
        missing = other_client.get(f"{ENTRIES_URL}{memory_id}/")
        self.assertEqual(missing.status_code, 404)

    def test_workbench_routes_are_gone(self):
        for path in (
            "/api/v1/ai/memory/overview/",
            "/api/v1/ai/memory/settings/",
            "/api/v1/ai/memory/documents/",
            "/api/v1/ai/memory/traces/",
            "/api/v1/ai/memory/runs/",
        ):
            response = self.client_api.get(path)
            self.assertEqual(response.status_code, 404, path)


class MemoryCeleryIndependenceTests(TestCase):
    def test_create_and_read_do_not_import_memory_tasks(self):
        import sys

        self.assertNotIn("chat_sync.ai_tasks.memory_tasks", sys.modules)
        user = get_user_model().objects.create_user(username="mem-no-celery")
        client_api = APIClient()
        client_api.force_authenticate(user)
        created = client_api.post(ENTRIES_URL, {"content": "以后请用中文回答。"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        listed = client_api.get(ENTRIES_URL)
        self.assertEqual(len(listed.json()["data"]["items"]), 1)
        self.assertNotIn("chat_sync.ai_tasks.memory_tasks", sys.modules)
