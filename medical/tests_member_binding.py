from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from file_manager.business_relations import bind_file_to_business
from file_manager.models import ManagedFile
from medical.models import HealthExamReport, MedExamDetail, Member, UserMemberBinding
from medical.services import member_binding_service as binding_service
from medical.services import member_share_ticket as share_ticket_service

User = get_user_model()


class MemberBindingAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", email="owner@example.com", password="pass12345")
        self.guest = User.objects.create_user(username="guest", email="guest@example.com", password="pass12345")
        self.client.force_authenticate(self.owner)
        create_resp = self.client.post(
            "/api/v1/medical/members/",
            {
                "name": "张三",
                "gender": "male",
                "relationship": "father",
                "is_primary": True,
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.member_id = create_resp.json()["data"]["id"]

    def test_list_includes_binding_capabilities(self):
        response = self.client.get("/api/v1/medical/members/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.json()["data"][0]
        self.assertIn("binding_id", row)
        self.assertEqual(row["relationship"], "father")
        self.assertTrue(row["can_share"])

    def test_share_accept_creates_binding_for_guest(self):
        ticket_resp = self.client.post(
            f"/api/v1/medical/members/{self.member_id}/share-ticket/",
            {"channel": "qr", "role": "viewer"},
            format="json",
        )
        ticket = ticket_resp.json()["data"]["share_ticket"]

        self.client.force_authenticate(self.guest)
        resolve_resp = self.client.post(
            "/api/v1/medical/member-share-ticket/resolve/",
            {"share_ticket": ticket},
            format="json",
        )
        self.assertEqual(resolve_resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resolve_resp.json()["data"]["already_bound"])

        accept_resp = self.client.post(
            "/api/v1/medical/member-share-ticket/accept/",
            {"share_ticket": ticket, "relationship": "son"},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(accept_resp.json()["data"]["relationship"], "son")

        guest_bindings = binding_service.active_bindings_qs().filter(user=self.guest, member_id=self.member_id)
        self.assertEqual(guest_bindings.count(), 1)

    def test_guest_cannot_access_without_binding(self):
        stranger = User.objects.create_user(username="stranger", email="s@example.com", password="pass12345")
        self.client.force_authenticate(stranger)
        response = self.client.get(f"/api/v1/medical/members/{self.member_id}/")
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_bound_guest_can_list_med_exam_details(self):
        ticket_resp = self.client.post(
            f"/api/v1/medical/members/{self.member_id}/share-ticket/",
            {"channel": "qr", "role": "viewer"},
            format="json",
        )
        ticket = ticket_resp.json()["data"]["share_ticket"]
        member = Member.objects.get(pk=self.member_id)
        report = HealthExamReport.objects.create(
            user=self.owner,
            member=member,
            institution_name="测试机构",
            report_no="R-001",
        )
        MedExamDetail.objects.create(
            member=member,
            business_type=MedExamDetail.BusinessType.HEALTH_EXAM_REPORT,
            business_id=report.id,
            item_name="白细胞",
            result_value="6.0",
        )

        self.client.force_authenticate(self.guest)
        accept_resp = self.client.post(
            "/api/v1/medical/member-share-ticket/accept/",
            {"share_ticket": ticket, "relationship": "son"},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, status.HTTP_200_OK)

        response = self.client.get(
            "/api/v1/medical/resources/",
            {
                "kind": "med-exam-details",
                "member_id": self.member_id,
                "business_type": MedExamDetail.BusinessType.HEALTH_EXAM_REPORT,
                "business_id": report.id,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]), 1)
        self.assertEqual(response.json()["data"][0]["item_name"], "白细胞")

    def test_bound_guest_can_see_report_attachments(self):
        ticket_resp = self.client.post(
            f"/api/v1/medical/members/{self.member_id}/share-ticket/",
            {"channel": "qr", "role": "viewer"},
            format="json",
        )
        ticket = ticket_resp.json()["data"]["share_ticket"]
        member = Member.objects.get(pk=self.member_id)
        report = HealthExamReport.objects.create(
            user=self.owner,
            member=member,
            institution_name="附件机构",
            report_no="ATT-001",
        )
        file_record = ManagedFile.objects.create(
            user=self.owner,
            original_name="report.pdf",
            mime_type="application/pdf",
            file_size=1024,
            object_key="medical/test/report.pdf",
        )
        bind_file_to_business(self.owner, file_record, "health_exam_report", report.id)

        self.client.force_authenticate(self.guest)
        accept_resp = self.client.post(
            "/api/v1/medical/member-share-ticket/accept/",
            {"share_ticket": ticket, "relationship": "son"},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, status.HTTP_200_OK)

        list_resp = self.client.get(
            "/api/v1/medical/resources/",
            {"kind": "health-exam-reports", "member_id": self.member_id},
        )
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        rows = list_resp.json()["data"]
        self.assertEqual(len(rows), 1)
        attachments = rows[0].get("attachments") or []
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]["original_name"], "report.pdf")

        download_resp = self.client.get(f"/api/v1/files/{file_record.id}/download-url/")
        self.assertEqual(download_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(download_resp.json()["data"]["url"])

    def test_bound_guest_can_save_medication_plan_workflow(self):
        ticket_resp = self.client.post(
            f"/api/v1/medical/members/{self.member_id}/share-ticket/",
            {"channel": "qr", "role": "viewer"},
            format="json",
        )
        ticket = ticket_resp.json()["data"]["share_ticket"]

        self.client.force_authenticate(self.guest)
        accept_resp = self.client.post(
            "/api/v1/medical/member-share-ticket/accept/",
            {"share_ticket": ticket, "relationship": "son"},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, status.HTTP_200_OK)

        save_resp = self.client.post(
            "/api/v1/medical/workflows/medication-plans/save/",
            {
                "member": self.member_id,
                "file_ids": [],
                "prescription": {
                    "institution_name": "测试医院",
                    "prescribed_at": "2026-05-20",
                    "diagnosis": "测试诊断",
                    "status": "active",
                },
                "items": [
                    {
                        "drug_name": "测试药品",
                        "dose_per_time": "1片",
                        "dose_unit": "片",
                        "frequency_type": "daily",
                        "frequency_text": "每日一次",
                        "start_date": "2026-05-21",
                        "status": "active",
                        "medicine_box": {
                            "medicine_name": "测试药品",
                            "dose_unit": "片",
                        },
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(save_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(save_resp.json()["code"], 0)
        self.assertTrue(save_resp.json()["data"]["items"])

    def test_tampered_ticket_rejected(self):
        ticket_resp = self.client.post(
            f"/api/v1/medical/members/{self.member_id}/share-ticket/",
            {"channel": "qr"},
            format="json",
        )
        ticket = ticket_resp.json()["data"]["share_ticket"] + "tampered"
        self.client.force_authenticate(self.guest)
        response = self.client.post(
            "/api/v1/medical/member-share-ticket/resolve/",
            {"share_ticket": ticket},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["msg"], "share_ticket_invalid")
