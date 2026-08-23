"""对话引导卡片科普问题登记 / 点击统计接口测试（BACKOFFICE-CONVERSATION-000001）。"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from medical.models import ChatGuideGeneratedQuestionRecord

User = get_user_model()


class ChatGuideQuestionAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", email="o@example.com", password="pass12345")
        self.other = User.objects.create_user(username="other", email="x@example.com", password="pass12345")

    def _create_member(self, user, name: str) -> int:
        self.client.force_authenticate(user)
        resp = self.client.post(
            "/api/v1/medical/members/",
            {"name": name, "gender": "male", "relationship": "self"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        return resp.json()["data"]["id"]

    def _register(self, user, member_id: int, questions):
        self.client.force_authenticate(user)
        return self.client.post(
            "/api/v1/medical/chat-guide/questions/register/",
            {"member_id": member_id, "questions": questions},
            format="json",
        )

    def test_register_creates_records_and_returns_server_ids(self):
        member_id = self._create_member(self.owner, "张三")
        resp = self._register(
            self.owner,
            member_id,
            [
                {"id": "q_1", "title": "久坐护颈", "prompt": "如何护颈？", "category": "popular_science"},
                {"id": "q_2", "title": "护腰", "prompt": "如何护腰？"},
            ],
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        self.assertEqual(data["registered"], 2)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["items"][0]["client_question_id"], "q_1")
        self.assertTrue(data["items"][0]["server_question_id"] > 0)

        records = ChatGuideGeneratedQuestionRecord.objects.filter(user=self.owner, member_id=member_id)
        self.assertEqual(records.count(), 2)
        # 未提供 category 的项回落默认值
        self.assertEqual(records.get(title="护腰").category, "popular_science")

    def test_register_forbidden_without_member_access(self):
        member_id = self._create_member(self.owner, "李四")
        resp = self._register(
            self.other,
            member_id,
            [{"id": "q_1", "title": "护颈", "prompt": "如何护颈？"}],
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            ChatGuideGeneratedQuestionRecord.objects.filter(member_id=member_id).count(),
            0,
        )

    def test_register_requires_auth(self):
        resp = self.client.post(
            "/api/v1/medical/chat-guide/questions/register/",
            {"member_id": 1, "questions": [{"title": "x", "prompt": "y"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_click_increments_atomically(self):
        member_id = self._create_member(self.owner, "王五")
        resp = self._register(self.owner, member_id, [{"id": "q_1", "title": "护颈", "prompt": "如何护颈？"}])
        server_question_id = resp.json()["data"]["items"][0]["server_question_id"]

        self.client.force_authenticate(self.owner)
        click = self.client.post(
            "/api/v1/medical/chat-guide/questions/click/",
            {"server_question_id": server_question_id},
            format="json",
        )
        self.assertEqual(click.status_code, status.HTTP_200_OK)
        self.assertTrue(click.json()["data"]["accepted"])
        self.assertEqual(click.json()["data"]["click_count"], 1)

        ChatGuideGeneratedQuestionRecord.objects.get(pk=server_question_id)

        # 再次点击再次 +1
        self.client.post(
            "/api/v1/medical/chat-guide/questions/click/",
            {"server_question_id": server_question_id},
            format="json",
        )
        self.assertEqual(
            ChatGuideGeneratedQuestionRecord.objects.get(pk=server_question_id).click_count,
            2,
        )

    def test_click_missing_or_foreign_record_ignored(self):
        member_id = self._create_member(self.owner, "赵六")
        resp = self._register(self.owner, member_id, [{"id": "q_1", "title": "护颈", "prompt": "如何护颈？"}])
        server_question_id = resp.json()["data"]["items"][0]["server_question_id"]

        # 他人无法对不属于自己的记录 +1
        self.client.force_authenticate(self.other)
        click = self.client.post(
            "/api/v1/medical/chat-guide/questions/click/",
            {"server_question_id": server_question_id},
            format="json",
        )
        self.assertEqual(click.status_code, status.HTTP_200_OK)
        self.assertFalse(click.json()["data"]["accepted"])
        self.assertEqual(
            ChatGuideGeneratedQuestionRecord.objects.get(pk=server_question_id).click_count,
            0,
        )

    def test_click_missing_record_returns_ignored(self):
        self.client.force_authenticate(self.owner)
        click = self.client.post(
            "/api/v1/medical/chat-guide/questions/click/",
            {"server_question_id": 999999},
            format="json",
        )
        self.assertEqual(click.status_code, status.HTTP_200_OK)
        self.assertFalse(click.json()["data"]["accepted"])