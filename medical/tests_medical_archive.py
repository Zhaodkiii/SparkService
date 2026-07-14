"""医疗档案归档 MEDICAL-ARCHIVE-000001 接口测试。"""

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from medical.models import MedicalCase, MedicationPlan, MedicineBox


class MedicalArchiveAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="archive_user",
            email="archive@example.com",
            password="test123456",
        )
        self.client.force_authenticate(self.user)
        create_resp = self.client.post(
            "/api/v1/medical/members/",
            {"name": "归档成员", "gender": "male", "relationship": "self"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.member_id = create_resp.json()["data"]["id"]
        self.case = MedicalCase.objects.create(
            user=self.user,
            member_id=self.member_id,
            title="普通病历",
            record_type="custom",
        )

    def test_list_defaults_to_active_only(self):
        archived = MedicalCase.objects.create(
            user=self.user,
            member_id=self.member_id,
            title="已归档病历",
            record_type="custom",
        )
        archived.archive()

        response = self.client.get(f"/api/v1/medical/resources/?kind=cases&member_id={self.member_id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.json()["data"]}
        self.assertIn(self.case.id, ids)
        self.assertNotIn(archived.id, ids)

    def test_list_archived_true(self):
        self.case.archive()
        response = self.client.get(
            f"/api/v1/medical/resources/?kind=cases&member_id={self.member_id}&archived=true"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.json()["data"]}
        self.assertEqual(ids, {self.case.id})
        self.assertTrue(response.json()["data"][0]["is_archived"])
        self.assertIsNotNone(response.json()["data"][0]["archived_at"])

    def test_list_archived_all(self):
        archived = MedicalCase.objects.create(
            user=self.user,
            member_id=self.member_id,
            title="归档二",
            record_type="custom",
        )
        archived.archive()
        response = self.client.get(
            f"/api/v1/medical/resources/?kind=cases&member_id={self.member_id}&archived=all"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.json()["data"]}
        self.assertEqual(ids, {self.case.id, archived.id})

    def test_invalid_archived_param(self):
        response = self.client.get(
            f"/api/v1/medical/resources/?kind=cases&member_id={self.member_id}&archived=maybe"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_archive_and_unarchive_idempotent(self):
        response = self.client.patch(
            f"/api/v1/medical/resources/{self.case.id}/?kind=cases",
            {"is_archived": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        data = response.json()["data"]
        self.assertTrue(data["is_archived"])
        self.assertIsNotNone(data["archived_at"])

        self.case.refresh_from_db()
        first_ts = self.case.archived_at

        response2 = self.client.patch(
            f"/api/v1/medical/resources/{self.case.id}/?kind=cases",
            {"is_archived": True},
            format="json",
        )
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.case.refresh_from_db()
        self.assertEqual(self.case.archived_at, first_ts)

        response3 = self.client.patch(
            f"/api/v1/medical/resources/{self.case.id}/?kind=cases",
            {"is_archived": False},
            format="json",
        )
        self.assertEqual(response3.status_code, status.HTTP_200_OK)
        data3 = response3.json()["data"]
        self.assertFalse(data3["is_archived"])
        self.assertIsNone(data3["archived_at"])

    def test_retrieve_allows_archived(self):
        self.case.archive()
        response = self.client.get(f"/api/v1/medical/resources/{self.case.id}/?kind=cases")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["data"]["is_archived"])

    def test_complete_data_excludes_archived(self):
        self.case.archive()
        box = MedicineBox.objects.create(
            user=self.user,
            member_id=self.member_id,
            medicine_name="阿莫西林",
        )
        box.archive()
        response = self.client.get(f"/api/v1/medical/members/{self.member_id}/complete-data/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()["data"]
        self.assertEqual(payload["medical_cases"], [])
        self.assertEqual(payload["medicine_boxes"], [])

    def test_family_cabinet_excludes_archived(self):
        box = MedicineBox.objects.create(
            user=self.user,
            member_id=self.member_id,
            medicine_name="布洛芬",
        )
        box.archive()
        response = self.client.get(
            f"/api/v1/medical/medicine-cabinet/summary/?member_id={self.member_id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.json()["data"]}
        self.assertNotIn(box.id, ids)

    def test_archive_medication_plan_excludes_from_enabled_reminders(self):
        plan = MedicationPlan.objects.create(
            user=self.user,
            member_id=self.member_id,
            drug_name="维生素C",
            frequency_type="daily",
            frequency_text="每天",
            reminder_times=[{"time": "08:00"}],
            start_date=timezone.localdate(),
            reminder_enabled=True,
            status=MedicationPlan.Status.ACTIVE,
        )
        plan.archive()
        response = self.client.get("/api/v1/medical/medication-reminders/enabled-plans/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        members = response.json()["data"].get("members") or []
        plan_ids = {
            item["id"]
            for group in members
            for item in (group.get("plans") or [])
        }
        self.assertNotIn(plan.id, plan_ids)
