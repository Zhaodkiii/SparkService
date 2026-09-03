from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import SocialIdentity
from medical.models import MemberMedicalProfile

from hospital_care.models import ClinicalConversationBinding
from hospital_care.services.conversation_service import create_patient_conversation
from hospital_care.tests.factories import (
    DummyRequest,
    make_agent,
    make_department,
    make_doctor,
    make_hospital,
    make_member,
    make_user,
)


class PatientWorkspaceApiTests(TestCase):
    """DOCTOR-WORKSPACE-000001：患者列表/工作台/会话/AI 总结/风险卡片。"""

    def setUp(self):
        self.client = APIClient()
        self.patient = make_user("pw-patient")
        self.member = make_member(self.patient, name="演示患者")
        self.member.gender = "female"
        self.member.birth_date = __import__("datetime").date(1990, 6, 15)
        self.member.blood_type = "A"
        self.member.save(update_fields=["gender", "birth_date", "blood_type", "updated_at"])

        self.hospital = make_hospital(code="PW-H")
        self.department = make_department(self.hospital)
        self.doctor_user = make_user("pw-doc")
        self.doctor = make_doctor(self.hospital, user=self.doctor_user, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.binding = create_patient_conversation(
            request=DummyRequest(self.patient),
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
        )
        self.client.force_authenticate(self.doctor_user)

    # ---------- D-007~D-010 患者列表 ----------

    def test_patient_list_visibility_counts_and_fields(self):
        response = self.client.get("/api/hospital/v1/doctor/patients/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["pagination"]["total"], 1)
        self.assertEqual(data["counts"], {"all": 1, "priority": 0, "pending": 0, "ended": 0})
        item = data["items"][0]
        self.assertEqual(item["member_id"], self.member.id)
        self.assertEqual(item["display_name"], "演示患者")
        self.assertTrue(item["masked_patient_identifier"].startswith("P"))
        self.assertIn("****", item["masked_patient_identifier"])
        self.assertEqual(item["service_status"], ClinicalConversationBinding.ServiceStatus.AI_ACTIVE)
        self.assertFalse(item["priority_patient"])
        self.assertEqual(item["available_conversation_count"], 1)
        self.assertIsNotNone(item["latest_conversation_at"])

    def test_patient_list_search_and_queue_filter(self):
        hit = self.client.get("/api/hospital/v1/doctor/patients/?keyword=演示")
        self.assertEqual(hit.data["data"]["pagination"]["total"], 1)
        miss = self.client.get("/api/hospital/v1/doctor/patients/?keyword=不存在")
        self.assertEqual(miss.data["data"]["pagination"]["total"], 0)

        # 重点患者筛选
        self.binding.doctor_attention_level = ClinicalConversationBinding.AttentionLevel.PRIORITY
        self.binding.save(update_fields=["doctor_attention_level", "updated_at"])
        priority = self.client.get("/api/hospital/v1/doctor/patients/?queue=priority")
        self.assertEqual(priority.data["data"]["pagination"]["total"], 1)
        self.assertEqual(priority.data["data"]["counts"]["priority"], 1)

        # 已结束筛选：重点标记在结束后不再计入 priority
        self.binding.service_status = ClinicalConversationBinding.ServiceStatus.ENDED
        self.binding.save(update_fields=["service_status", "updated_at"])
        ended = self.client.get("/api/hospital/v1/doctor/patients/?queue=ended")
        self.assertEqual(ended.data["data"]["pagination"]["total"], 1)
        self.assertEqual(ended.data["data"]["counts"]["priority"], 0)
        still_priority = self.client.get("/api/hospital/v1/doctor/patients/?queue=priority")
        self.assertEqual(still_priority.data["data"]["pagination"]["total"], 0)

    def test_patient_list_priority_sorted_first(self):
        other_user = make_user("pw-patient-2")
        other_member = make_member(other_user, name="第二患者")
        second = create_patient_conversation(
            request=DummyRequest(other_user),
            user=other_user,
            agent_id=self.agent.id,
            member_id=other_member.id,
        )
        # 第二患者会话更新，但第一患者是重点患者，应排在最前。
        second.save()
        self.binding.doctor_attention_level = ClinicalConversationBinding.AttentionLevel.PRIORITY
        self.binding.save(update_fields=["doctor_attention_level", "updated_at"])

        response = self.client.get("/api/hospital/v1/doctor/patients/")
        items = response.data["data"]["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["member_id"], self.member.id)
        self.assertTrue(items[0]["priority_patient"])

    def test_patient_list_excludes_other_doctors_patients(self):
        other_user = make_user("pw-doc-other")
        make_doctor(self.hospital, user=other_user, department=self.department, display_name="其他医生")
        self.client.force_authenticate(other_user)
        response = self.client.get("/api/hospital/v1/doctor/patients/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["pagination"]["total"], 0)

    # ---------- D-004/D-006 患者工作台聚合快照 ----------

    def _make_profile(self):
        return MemberMedicalProfile.objects.create(
            user=self.patient,
            member=self.member,
            allergies=["青霉素"],
            chronic_conditions=["高血压"],
            smoking_profile={"status": "never"},
            drinking_profile={"status": "occasional"},
            medication_focus=[{"drug_name": "苯磺酸氨氯地平", "summary": "降压"}],
            extra={"height_cm": "165", "weight_kg": "60", "region": "安徽滁州", "occupation": "教师"},
        )

    def test_workspace_snapshot_and_masking(self):
        SocialIdentity.objects.create(
            user=self.patient,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid="13812345678",
        )
        self._make_profile()

        response = self.client.get(f"/api/hospital/v1/doctor/patients/{self.member.id}/workspace/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]

        patient = data["patient"]
        self.assertEqual(patient["member_id"], self.member.id)
        self.assertEqual(patient["display_name"], "演示患者")
        self.assertEqual(patient["gender"], "female")
        self.assertEqual(patient["age"], 36)
        self.assertTrue(patient["patient_number"].startswith("P"))
        self.assertEqual(patient["service_status"], ClinicalConversationBinding.ServiceStatus.AI_ACTIVE)

        basic = data["basic_profile"]
        self.assertEqual(basic["phone_masked"], "138****5678")
        self.assertNotIn("13812345678", str(response.data))
        self.assertEqual(basic["region"], "安徽滁州")
        self.assertEqual(basic["occupation"], "教师")

        health = data["health_profile"]
        self.assertEqual(health["height_cm"], 165.0)
        self.assertEqual(health["weight_kg"], 60.0)
        self.assertEqual(health["bmi"], 22.0)
        self.assertEqual(health["blood_type"], "A")
        self.assertEqual(health["smoking_status"], "never")

        safety = data["medical_safety"]
        self.assertEqual(safety["allergies"], ["青霉素"])
        self.assertEqual(safety["long_term_medications"], ["苯磺酸氨氯地平 · 降压"])
        self.assertEqual(safety["past_medical_history"], ["高血压"])

        self.assertEqual(data["work_flags"], {"priority_patient": False})
        self.assertIn("snapshot_at", data["freshness"])

    def test_workspace_missing_profile_returns_null_fields(self):
        response = self.client.get(f"/api/hospital/v1/doctor/patients/{self.member.id}/workspace/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertIsNone(data["basic_profile"]["phone_masked"])
        self.assertIsNone(data["health_profile"]["height_cm"])
        self.assertEqual(data["medical_safety"]["allergies"], [])

    # ---------- 只读边界与权限 ----------

    def test_unassigned_member_forbidden_everywhere(self):
        stranger = make_member(make_user("pw-stranger"), name="无关患者")
        urls = [
            f"/api/hospital/v1/doctor/patients/{stranger.id}/workspace/",
            f"/api/hospital/v1/doctor/patients/{stranger.id}/conversations/",
            f"/api/hospital/v1/doctor/patients/{stranger.id}/summary/",
            f"/api/hospital/v1/doctor/patients/{stranger.id}/risk/",
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, url)
            self.assertEqual(response.data["msg"], "PATIENT_NOT_ASSIGNED", url)

        post_cases = [
            (f"/api/hospital/v1/doctor/patients/{stranger.id}/conversations/", {}),
            (f"/api/hospital/v1/doctor/patients/{stranger.id}/summary/generate/", {}),
            (f"/api/hospital/v1/doctor/patients/{stranger.id}/summary/ack/", {"acknowledged": True}),
        ]
        for url, payload in post_cases:
            response = self.client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY=f"forbidden-{url}")
            self.assertEqual(response.status_code, 403, url)
            self.assertEqual(response.data["msg"], "PATIENT_NOT_ASSIGNED", url)

    def test_non_doctor_forbidden(self):
        self.client.force_authenticate(self.patient)
        response = self.client.get("/api/hospital/v1/doctor/patients/")
        self.assertEqual(response.status_code, 403)

    # ---------- D-012/D-013/D-019 患者会话 ----------

    def test_patient_conversations_list(self):
        response = self.client.get(f"/api/hospital/v1/doctor/patients/{self.member.id}/conversations/")
        self.assertEqual(response.status_code, 200)
        items = response.data["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["thread_id"], str(self.binding.thread_id))

    def test_create_conversation_inherits_patient_and_agent(self):
        response = self.client.post(
            f"/api/hospital/v1/doctor/patients/{self.member.id}/conversations/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="pw-create-1",
        )
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data["data"]
        self.assertNotEqual(data["thread_id"], str(self.binding.thread_id))
        self.assertEqual(data["service_status"], ClinicalConversationBinding.ServiceStatus.AI_ACTIVE)

        new_binding = ClinicalConversationBinding.objects.get(thread_id=data["thread_id"])
        self.assertEqual(new_binding.doctor_id, self.doctor.id)
        self.assertEqual(new_binding.agent_id, self.agent.id)
        self.assertEqual(new_binding.thread.member_id, self.member.id)
        self.assertEqual(new_binding.hospital_id, self.hospital.id)

        replay = self.client.post(
            f"/api/hospital/v1/doctor/patients/{self.member.id}/conversations/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="pw-create-1",
        )
        self.assertEqual(replay.data["data"]["thread_id"], data["thread_id"])

        listing = self.client.get(f"/api/hospital/v1/doctor/patients/{self.member.id}/conversations/")
        self.assertEqual(len(listing.data["data"]["items"]), 2)

    # ---------- D-020~D-023 AI 总结 ----------

    def test_summary_generate_and_ack_flow(self):
        # 进入页面不自动生成：首次查询为空。
        empty = self.client.get(f"/api/hospital/v1/doctor/patients/{self.member.id}/summary/")
        self.assertEqual(empty.status_code, 200)
        self.assertIsNone(empty.data["data"])

        created = self.client.post(
            f"/api/hospital/v1/doctor/patients/{self.member.id}/summary/generate/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="pw-summary-1",
        )
        self.assertEqual(created.status_code, 201, created.data)
        summary = created.data["data"]
        self.assertEqual(summary["version"], 1)
        self.assertTrue(summary["system_generated"])
        self.assertFalse(summary["acknowledged"])
        self.assertEqual(summary["tool_name"], "patient-workspace-summary-v1")
        for key in ("current_issues", "key_health_info", "conversation_highlights", "follow_up_items"):
            self.assertIn(key, summary["sections"])
        self.assertEqual(summary["data_scope"]["thread_count"], 1)

        latest = self.client.get(f"/api/hospital/v1/doctor/patients/{self.member.id}/summary/")
        self.assertEqual(latest.data["data"]["id"], summary["id"])

        # 再次生成产生新版本。
        regenerated = self.client.post(
            f"/api/hospital/v1/doctor/patients/{self.member.id}/summary/generate/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="pw-summary-2",
        )
        self.assertEqual(regenerated.data["data"]["version"], 2)

        # 已了解 / 取消已了解。
        acked = self.client.post(
            f"/api/hospital/v1/doctor/patients/{self.member.id}/summary/ack/",
            {"acknowledged": True},
            format="json",
            HTTP_IDEMPOTENCY_KEY="pw-ack-1",
        )
        self.assertEqual(acked.status_code, 200, acked.data)
        self.assertTrue(acked.data["data"]["acknowledged"])
        self.assertEqual(acked.data["data"]["version"], 2)
        self.assertIsNotNone(acked.data["data"]["acknowledged_at"])

        unacked = self.client.post(
            f"/api/hospital/v1/doctor/patients/{self.member.id}/summary/ack/",
            {"acknowledged": False},
            format="json",
            HTTP_IDEMPOTENCY_KEY="pw-ack-2",
        )
        self.assertFalse(unacked.data["data"]["acknowledged"])

    def test_ack_without_summary_unavailable(self):
        response = self.client.post(
            f"/api/hospital/v1/doctor/patients/{self.member.id}/summary/ack/",
            {"acknowledged": True},
            format="json",
            HTTP_IDEMPOTENCY_KEY="pw-ack-empty",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["msg"], "SUMMARY_UNAVAILABLE")

    # ---------- D-024~D-026 风险卡片 ----------

    def test_risk_card_none_when_no_signal(self):
        response = self.client.get(f"/api/hospital/v1/doctor/patients/{self.member.id}/risk/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["data"])

    def test_risk_card_readonly_highest_signal(self):
        self.binding.risk_signal_level = ClinicalConversationBinding.RiskSignalLevel.LOW
        self.binding.save(update_fields=["risk_signal_level", "updated_at"])
        second = create_patient_conversation(
            request=DummyRequest(self.patient),
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
        )
        second.risk_signal_level = ClinicalConversationBinding.RiskSignalLevel.HIGH
        second.save(update_fields=["risk_signal_level", "updated_at"])

        response = self.client.get(f"/api/hospital/v1/doctor/patients/{self.member.id}/risk/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["level"], ClinicalConversationBinding.RiskSignalLevel.HIGH)
        self.assertEqual(data["status"], "effective")
        self.assertEqual(data["source"], "existing_risk_tool")
        self.assertEqual(data["source_thread_id"], str(second.thread_id))
        self.assertIn("现有风险工具", data["suggestion"])
        self.assertIsNotNone(data["data_cutoff_at"])
