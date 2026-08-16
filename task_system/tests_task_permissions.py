from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from medical.models import Member, UserMemberBinding
from medical.services import member_binding_service as binding_service
from task_system.models import Task, TaskMedical

User = get_user_model()


class TaskMemberPermissionAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="task_owner", email="task-owner@example.com", password="pass12345")
        self.editor = User.objects.create_user(username="task_editor", email="task-editor@example.com", password="pass12345")
        self.viewer = User.objects.create_user(username="task_viewer", email="task-viewer@example.com", password="pass12345")
        self.stranger = User.objects.create_user(username="task_stranger", email="task-stranger@example.com", password="pass12345")
        self.member = Member.objects.create(user=self.owner, name="任务成员", gender="male", is_primary=True)
        binding_service.create_owner_binding(user=self.owner, member=self.member, relationship="self")
        binding_service.accept_share_binding(
            user=self.editor,
            member=self.member,
            relationship="family",
            custom_relationship="",
            role=UserMemberBinding.Role.EDITOR,
            invited_by=self.owner,
        )
        binding_service.accept_share_binding(
            user=self.viewer,
            member=self.member,
            relationship="family",
            custom_relationship="",
            role=UserMemberBinding.Role.VIEWER,
            invited_by=self.owner,
        )

    def _medical_task_payload(self):
        now = timezone.now()
        return {
            "member": self.member.id,
            "title": "入睡时间",
            "description": "23:00 前上床准备入睡",
            "type": 0,
            "status": 0,
            "start_time": now.isoformat(),
            "due_time": (now + timedelta(days=1)).isoformat(),
            "repeat_type": 1,
            "priority": 1,
            "business_type": "ai_task_generation",
            "business_id": "",
            "extra": {},
            "task_medical": {
                "reminder_time": now.isoformat(),
                "medical_task_type": "睡眠管理",
                "description": "记录入睡时间和起床时间",
                "source": "ai",
                "extra": {},
            },
        }

    def test_editor_binding_can_create_task_for_shared_member(self):
        self.client.force_authenticate(self.editor)

        response = self.client.post("/api/v1/tasks/", self._medical_task_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()["data"]
        self.assertEqual(body["member"], self.member.id)
        self.assertEqual(Task.objects.filter(member=self.member, creator=self.editor).count(), 1)
        self.assertEqual(TaskMedical.objects.filter(task_id=body["id"], medical_task_type="睡眠管理").count(), 1)
        self.assertTrue(body["notification_enabled"])

    def test_notification_enabled_can_be_disabled_and_synced(self):
        self.client.force_authenticate(self.owner)
        created = self.client.post("/api/v1/tasks/", self._medical_task_payload(), format="json").json()["data"]

        response = self.client.patch(
            f"/api/v1/tasks/{created['id']}/",
            {"notification_enabled": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.json()["data"]["notification_enabled"])
        sync = self.client.get("/api/v1/tasks/sync/").json()["data"]
        self.assertFalse(sync["tasks"][0]["notification_enabled"])
        self.assertFalse(sync["task_statuses"][0]["notification_enabled"])

    def test_enabled_notification_requires_effective_time(self):
        self.client.force_authenticate(self.owner)
        payload = self._medical_task_payload()
        payload["start_time"] = None
        payload["due_time"] = None
        payload["task_medical"]["reminder_time"] = None

        response = self.client.post("/api/v1/tasks/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("notification_enabled", response.json()["data"])

    def test_disabled_notification_allows_task_without_time(self):
        self.client.force_authenticate(self.owner)
        payload = self._medical_task_payload()
        payload["notification_enabled"] = False
        payload["start_time"] = None
        payload["due_time"] = None
        payload["task_medical"]["reminder_time"] = None

        response = self.client.post("/api/v1/tasks/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.json()["data"]["notification_enabled"])

    def test_viewer_binding_cannot_create_task_for_shared_member(self):
        self.client.force_authenticate(self.viewer)

        response = self.client.post("/api/v1/tasks/", self._medical_task_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        body = response.json()
        self.assertEqual(body["msg"], "permission_denied")
        self.assertEqual(body["data"]["code"], "member_permission_denied")

    def test_stranger_cannot_list_or_sync_shared_member_tasks(self):
        Task.objects.create(member=self.member, creator=self.owner, title="已有任务", description="", type=0)
        self.client.force_authenticate(self.stranger)

        list_response = self.client.get("/api/v1/tasks/")
        sync_response = self.client.get("/api/v1/tasks/sync/")
        member_response = self.client.get("/api/v1/tasks/", {"member_id": self.member.id})

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.json()["data"], [])
        self.assertEqual(sync_response.status_code, status.HTTP_200_OK)
        self.assertEqual(sync_response.json()["data"]["tasks"], [])
        self.assertEqual(member_response.status_code, status.HTTP_404_NOT_FOUND)
