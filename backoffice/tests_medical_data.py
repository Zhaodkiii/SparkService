from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from backoffice.medical_data_stats_service import refresh_global_stats, refresh_member_stats, refresh_user_stats
from backoffice.models import AdminRole, AdminUserRole
from backoffice.rbac import bootstrap_admin_permissions
from file_manager.models import ManagedFile, ManagedFileBusinessRelation
from medical.models import HealthExamReport, MedicalCase, Member, UserMemberBinding

User = get_user_model()


class AdminMedicalDataTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.superuser = User.objects.create_user(
            username="medical_super",
            email="medical_super@example.com",
            password="pass1234",
            is_staff=True,
            is_superuser=True,
        )
        self.medical_user = User.objects.create_user(
            username="medical_owner",
            email="owner@example.com",
            password="pass1234",
        )
        bootstrap_admin_permissions()

        self.member = Member.objects.create(
            user=self.medical_user,
            name="张三",
            gender="male",
            birth_date=date(1990, 1, 1),
            is_primary=True,
        )
        UserMemberBinding.objects.create(
            user=self.medical_user,
            member=self.member,
            relationship="self",
            role=UserMemberBinding.Role.OWNER,
        )
        self.medical_case = MedicalCase.objects.create(
            user=self.medical_user,
            member=self.member,
            title="感冒就诊",
            diagnosis_summary="上呼吸道感染",
        )
        self.health_exam = HealthExamReport.objects.create(
            user=self.medical_user,
            member=self.member,
            institution_name="市体检中心",
            exam_date=timezone.localdate(),
            source=HealthExamReport.Source.OCR,
        )

        refresh_member_stats(self.member.id)
        refresh_user_stats(self.medical_user.id)
        refresh_global_stats()

    def test_global_stats_endpoint(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get("/api/admin/v1/medical-data/stats/global/")
        self.assertEqual(response.status_code, 200)
        stats = response.json()["data"]["stats"]
        self.assertGreaterEqual(stats["medical_data_total"], 2)
        self.assertIn("meta", response.json()["data"])

    def test_user_list_requires_auth(self):
        response = self.client.get("/api/admin/v1/medical-data/users/")
        self.assertEqual(response.status_code, 401)

    def test_user_list_returns_medical_users(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get("/api/admin/v1/medical-data/users/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        user_ids = [row["user_id"] for row in payload["items"]]
        self.assertIn(self.medical_user.id, user_ids)
        self.assertIn("meta", payload)

    def test_user_members_includes_empty_member_by_default(self):
        empty_member = Member.objects.create(
            user=self.medical_user,
            name="李四",
            gender="female",
            birth_date=date(1995, 5, 5),
            is_primary=False,
        )
        UserMemberBinding.objects.create(
            user=self.medical_user,
            member=empty_member,
            relationship="spouse",
            role=UserMemberBinding.Role.EDITOR,
        )
        refresh_member_stats(empty_member.id)
        refresh_user_stats(self.medical_user.id)

        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(f"/api/admin/v1/medical-data/users/{self.medical_user.id}/members/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        member_ids = {row["member_id"] for row in payload["members"]}
        self.assertIn(self.member.id, member_ids)
        self.assertIn(empty_member.id, member_ids)
        self.assertEqual(payload["user"]["member_count"], 2)
        self.assertEqual(payload["user"]["members_with_data_count"], 1)

    def test_user_members_only_with_data_filters_when_requested(self):
        empty_member = Member.objects.create(
            user=self.medical_user,
            name="李四",
            gender="female",
            birth_date=date(1995, 5, 5),
            is_primary=False,
        )
        UserMemberBinding.objects.create(
            user=self.medical_user,
            member=empty_member,
            relationship="spouse",
            role=UserMemberBinding.Role.EDITOR,
        )
        refresh_member_stats(empty_member.id)
        refresh_user_stats(self.medical_user.id)

        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(
            f"/api/admin/v1/medical-data/users/{self.medical_user.id}/members/?only_with_data=true"
        )
        self.assertEqual(response.status_code, 200)
        member_ids = {row["member_id"] for row in response.json()["data"]["members"]}
        self.assertEqual(member_ids, {self.member.id})

    def test_user_members_and_lightweight_complete_data(self):
        self.client.force_authenticate(user=self.superuser)
        members_resp = self.client.get(f"/api/admin/v1/medical-data/users/{self.medical_user.id}/members/")
        self.assertEqual(members_resp.status_code, 200)
        members = members_resp.json()["data"]["members"]
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["gender_label"], "男")
        self.assertIn("pagination", members_resp.json()["data"])

        complete_resp = self.client.get(
            f"/api/admin/v1/medical-data/users/{self.medical_user.id}/members/{self.member.id}/complete-data/"
        )
        self.assertEqual(complete_resp.status_code, 200)
        complete = complete_resp.json()["data"]
        self.assertEqual(complete["category_counts"]["medical_cases"], 1)
        self.assertNotIn("timeline_preview", complete)
        self.assertNotIn("quality_flags", complete)
        self.assertIn("quality_flag_count", complete)

    def test_timeline_and_quality_endpoints(self):
        self.client.force_authenticate(user=self.superuser)
        timeline_resp = self.client.get(
            f"/api/admin/v1/medical-data/users/{self.medical_user.id}/members/{self.member.id}/timeline/"
        )
        self.assertEqual(timeline_resp.status_code, 200)
        self.assertIn("items", timeline_resp.json()["data"])

        quality_resp = self.client.get(
            f"/api/admin/v1/medical-data/users/{self.medical_user.id}/members/{self.member.id}/quality-flags/"
        )
        self.assertEqual(quality_resp.status_code, 200)
        self.assertIn("items", quality_resp.json()["data"])

    def test_resource_list_and_detail(self):
        self.client.force_authenticate(user=self.superuser)
        list_resp = self.client.get(
            f"/api/admin/v1/medical-data/users/{self.medical_user.id}/members/{self.member.id}/medical-cases/"
        )
        self.assertEqual(list_resp.status_code, 200)
        items = list_resp.json()["data"]["items"]
        self.assertEqual(len(items), 1)

        detail_resp = self.client.get(f"/api/admin/v1/medical-data/resources/medical-cases/{self.medical_case.id}/")
        self.assertEqual(detail_resp.status_code, 200)
        detail = detail_resp.json()["data"]
        self.assertEqual(detail["resource_id"], self.medical_case.id)

    def test_attachments_list(self):
        managed_file = ManagedFile.objects.create(
            user=self.medical_user,
            original_name="case-report.pdf",
            mime_type="application/pdf",
            file_size=1024,
        )
        ManagedFileBusinessRelation.objects.create(
            file=managed_file,
            user=self.medical_user,
            business_type="medical_case",
            business_id=str(self.medical_case.id),
        )
        refresh_member_stats(self.member.id)
        refresh_user_stats(self.medical_user.id)

        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(
            f"/api/admin/v1/medical-data/users/{self.medical_user.id}/members/{self.member.id}/attachments/"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["resource_type"], "attachments")
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["original_name"], "case-report.pdf")
        self.assertEqual(payload["items"][0]["business_type"], "medical_case")

    def test_attachments_list_user_scoped_not_member_scoped(self):
        valid_file = ManagedFile.objects.create(
            user=self.medical_user,
            original_name="valid-case.pdf",
            mime_type="application/pdf",
            file_size=100,
        )
        ManagedFileBusinessRelation.objects.create(
            file=valid_file,
            user=self.medical_user,
            business_type="medical_case",
            business_id=str(self.medical_case.id),
        )
        unlinked_file = ManagedFile.objects.create(
            user=self.medical_user,
            original_name="unlinked.jpg",
            mime_type="image/jpeg",
            file_size=100,
        )
        other_user = User.objects.create_user(
            username="other_medical_user",
            email="other@example.com",
            password="pass1234",
        )
        other_user_file = ManagedFile.objects.create(
            user=other_user,
            original_name="other-user.jpg",
            mime_type="image/jpeg",
            file_size=100,
        )
        ManagedFileBusinessRelation.objects.create(
            file=other_user_file,
            user=other_user,
            business_type="medical_case",
            business_id=str(self.medical_case.id),
        )

        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(
            f"/api/admin/v1/medical-data/users/{self.medical_user.id}/members/{self.member.id}/attachments/"
        )
        self.assertEqual(response.status_code, 200)
        names = {item["original_name"] for item in response.json()["data"]["items"]}
        self.assertIn("valid-case.pdf", names)
        self.assertIn("unlinked.jpg", names)
        self.assertNotIn("other-user.jpg", names)

    def test_shared_relations_audit(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(
            f"/api/admin/v1/medical-data/users/{self.medical_user.id}/members/{self.member.id}/shared-relations/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()["data"]["items"]), 1)
