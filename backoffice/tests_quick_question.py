"""快捷问题配置与生成记录后台接口测试（BACKOFFICE-CONVERSATION-000001）。"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from backoffice.rbac import bootstrap_admin_permissions
from medical.models import (
    ChatGuideGeneratedQuestionRecord,
    ChatGuideQuickQuestionConfig,
    Member,
)

User = get_user_model()

CONFIGS_URL = "/api/admin/v1/conversations/quick-questions/configs/"
RECORDS_URL = "/api/admin/v1/conversations/quick-questions/generated-records/"


class AdminQuickQuestionTests(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="super_admin",
            email="super@example.com",
            password="pass1234",
            is_staff=True,
            is_superuser=True,
        )
        self.chat_user = User.objects.create_user(
            username="chat_user",
            email="chat@example.com",
            password="pass1234",
        )
        bootstrap_admin_permissions()
        self.member = Member.objects.create(user=self.chat_user, name="张三", gender="male")

    def _auth_admin(self):
        self.client.force_authenticate(self.superuser)

    def test_permission_denied_for_non_superuser(self):
        self.client.force_authenticate(self.chat_user)
        resp = self.client.get(CONFIGS_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_config_create_list_update_enable_disable(self):
        self._auth_admin()

        create = self.client.post(
            CONFIGS_URL,
            {"title": "久坐护颈", "prompt": "如何保护颈椎？", "category": "popular_science", "is_active": True},
            format="json",
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        config_id = create.json()["data"]["id"]
        self.assertEqual(create.json()["data"]["created_by"], self.superuser.id)

        listing = self.client.get(CONFIGS_URL)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.json()["data"]["pagination"]["total"], 1)

        update = self.client.patch(
            f"{CONFIGS_URL}{config_id}/",
            {"title": "久坐护颈（更新）"},
            format="json",
        )
        self.assertEqual(update.status_code, status.HTTP_200_OK)
        self.assertTrue(update.json()["data"]["updated_by"] is not None)

        disable = self.client.post(f"{CONFIGS_URL}{config_id}/disable/")
        self.assertEqual(disable.status_code, status.HTTP_200_OK)
        self.assertFalse(disable.json()["data"]["is_active"])

        enable = self.client.post(f"{CONFIGS_URL}{config_id}/enable/")
        self.assertEqual(enable.status_code, status.HTTP_200_OK)
        self.assertTrue(enable.json()["data"]["is_active"])

    def test_config_filter_by_active_and_keyword(self):
        self._auth_admin()
        ChatGuideQuickQuestionConfig.objects.create(
            title="护颈", prompt="如何护颈？", is_active=True, created_by=self.superuser
        )
        ChatGuideQuickQuestionConfig.objects.create(
            title="护腰", prompt="如何护腰？", is_active=False, created_by=self.superuser
        )

        active = self.client.get(CONFIGS_URL, {"is_active": "true"})
        self.assertEqual(active.json()["data"]["pagination"]["total"], 1)
        self.assertEqual(active.json()["data"]["items"][0]["title"], "护颈")

        keyword = self.client.get(CONFIGS_URL, {"keyword": "护腰"})
        self.assertEqual(keyword.json()["data"]["pagination"]["total"], 1)
        self.assertEqual(keyword.json()["data"]["items"][0]["title"], "护腰")

    def test_generated_record_list_and_detail(self):
        self._auth_admin()
        record = ChatGuideGeneratedQuestionRecord.objects.create(
            user=self.chat_user,
            member=self.member,
            title="护颈",
            prompt="如何保护颈椎？",
            category="popular_science",
            click_count=3,
        )

        listing = self.client.get(RECORDS_URL)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.json()["data"]["pagination"]["total"], 1)
        item = listing.json()["data"]["items"][0]
        self.assertEqual(item["click_count"], 3)
        self.assertEqual(item["member_name"], "张三")
        self.assertEqual(item["user_name"], "chat_user")

        detail = self.client.get(f"{RECORDS_URL}{record.id}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        # 详情返回完整 prompt
        self.assertEqual(detail.json()["data"]["prompt"], "如何保护颈椎？")

    def test_generated_record_filter_by_member(self):
        self._auth_admin()
        ChatGuideGeneratedQuestionRecord.objects.create(
            user=self.chat_user, member=self.member, title="护颈", prompt="a"
        )
        other_member = Member.objects.create(user=self.chat_user, name="李四")
        ChatGuideGeneratedQuestionRecord.objects.create(
            user=self.chat_user, member=other_member, title="护腰", prompt="b"
        )

        listing = self.client.get(RECORDS_URL, {"member_id": str(self.member.id)})
        self.assertEqual(listing.json()["data"]["pagination"]["total"], 1)
        self.assertEqual(listing.json()["data"]["items"][0]["title"], "护颈")