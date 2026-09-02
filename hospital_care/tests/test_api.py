from django.test import TestCase
from rest_framework.test import APIClient

from hospital_care.models import ClinicalConversationBinding, Hospital
from hospital_care.services.conversation_service import create_patient_conversation, join_conversation
from hospital_care.tests.factories import (
    DummyRequest,
    make_agent,
    make_department,
    make_doctor,
    make_hospital,
    make_member,
    make_staff,
    make_user,
)
from hospital_care.models import HospitalStaffMembership


class PatientApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.patient = make_user("api-patient")
        self.member = make_member(self.patient)
        self.hospital = make_hospital(code="API-H")
        self.department = make_department(self.hospital)
        self.doctor_user = make_user("api-doc")
        self.doctor = make_doctor(self.hospital, user=self.doctor_user, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.client.force_authenticate(self.patient)

    def test_hospital_home_and_create_conversation(self):
        home = self.client.get(f"/api/v1/hospital-care/hospitals/{self.hospital.id}/home/?member_id={self.member.id}")
        self.assertEqual(home.status_code, 200)
        self.assertEqual(home.data["code"], 0)
        self.assertEqual(home.data["data"]["hospital"]["name"], self.hospital.name)
        self.assertNotIn("employee_no", str(home.data))

        response = self.client.post(
            "/api/v1/hospital-care/conversations/",
            {"agent_id": str(self.agent.id), "member_id": self.member.id},
            format="json",
            HTTP_IDEMPOTENCY_KEY="create-1",
        )
        self.assertEqual(response.status_code, 200, response.data)
        thread_id = response.data["data"]["thread_id"]
        context = self.client.get(f"/api/v1/hospital-care/conversations/{thread_id}/context/")
        self.assertEqual(context.status_code, 200)
        self.assertEqual(context.data["data"]["service_status"], ClinicalConversationBinding.ServiceStatus.AI_ACTIVE)

        replay = self.client.post(
            "/api/v1/hospital-care/conversations/",
            {"agent_id": str(self.agent.id), "member_id": self.member.id},
            format="json",
            HTTP_IDEMPOTENCY_KEY="create-1",
        )
        self.assertEqual(replay.data["data"]["thread_id"], thread_id)

    def test_illegal_member_rejected(self):
        stranger = make_user("api-stranger")
        stranger_member = make_member(stranger)
        response = self.client.post(
            "/api/v1/hospital-care/conversations/",
            {"agent_id": str(self.agent.id), "member_id": stranger_member.id},
            format="json",
            HTTP_IDEMPOTENCY_KEY="create-bad",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["msg"], "MEMBER_ACCESS_DENIED")

    def test_registration_integrated_unavailable(self):
        self.hospital.service_mode = Hospital.ServiceMode.INTEGRATED
        self.hospital.save(update_fields=["service_mode"])
        response = self.client.get(f"/api/v1/hospital-care/hospitals/{self.hospital.id}/registration/entry/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["msg"], "REGISTRATION_INTEGRATION_UNAVAILABLE")


class DoctorApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.patient = make_user("docapi-patient")
        self.member = make_member(self.patient)
        self.hospital = make_hospital(code="API-D")
        self.department = make_department(self.hospital)
        self.doctor_user = make_user("docapi-doc")
        self.doctor = make_doctor(self.hospital, user=self.doctor_user, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.binding = create_patient_conversation(
            request=DummyRequest(self.patient),
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
        )
        self.client.force_authenticate(self.doctor_user)

    def test_workspace_join_and_message(self):
        workspace = self.client.get("/api/hospital/v1/me/workspace/")
        self.assertEqual(workspace.status_code, 200)
        listing = self.client.get("/api/hospital/v1/doctor/conversations/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["data"]["pagination"]["total"], 1)

        joined = self.client.post(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/join/",
            {"version": self.binding.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="join-1",
        )
        self.assertEqual(joined.status_code, 200, joined.data)
        self.assertEqual(joined.data["data"]["service_status"], ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED)

        sent = self.client.post(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/messages/",
            {"text": "请立即停止活动", "version": joined.data["data"]["version"]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="msg-1",
        )
        self.assertEqual(sent.status_code, 200, sent.data)
        self.assertEqual(sent.data["data"]["sender"]["actor_type"], "doctor")
        self.assertNotIn("请立即停止活动", str(sent.data.get("msg")))

        messages = self.client.get(f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/messages/")
        actors = {item.get("actor_type") for item in messages.data["data"]["items"]}
        self.assertIn("doctor", actors)
        self.assertIn("system", actors)

    def test_other_doctor_forbidden(self):
        other = make_user("docapi-other")
        make_doctor(self.hospital, user=other, department=self.department, display_name="其他医生")
        self.client.force_authenticate(other)
        response = self.client.get(f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/")
        self.assertEqual(response.status_code, 403)


class BackofficeApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user("bo-admin", is_staff=True, is_superuser=True)
        self.client.force_authenticate(self.admin)

    def test_create_activate_and_list(self):
        created = self.client.post(
            "/api/admin/v1/hospital-care/hospitals/",
            {
                "code": "BO-1",
                "name": "后台医院",
                "province_code": "340000",
                "city_code": "341100",
                "address": "后台路 1 号",
                "service_mode": "demo",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="bo-create",
        )
        self.assertEqual(created.status_code, 201, created.data)
        hospital_id = created.data["data"]["id"]
        make_staff(
            Hospital.objects.get(pk=hospital_id),
            self.admin,
            HospitalStaffMembership.Role.HOSPITAL_ADMIN,
        )
        version = created.data["data"]["version"]
        activated = self.client.post(
            f"/api/admin/v1/hospital-care/hospitals/{hospital_id}/activate/",
            {"version": version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="bo-activate",
        )
        self.assertEqual(activated.status_code, 200, activated.data)
        self.assertEqual(activated.data["data"]["status"], Hospital.Status.ACTIVE)

        listing = self.client.get("/api/admin/v1/hospital-care/hospitals/")
        self.assertEqual(listing.status_code, 200)
        self.assertGreaterEqual(listing.data["data"]["pagination"]["total"], 1)
        self.assertEqual(listing.data["code"], 0)

    def test_update_staff(self):
        hospital = make_hospital(code="BO-STAFF")
        nurse = make_staff(hospital, make_user("bo-nurse"), HospitalStaffMembership.Role.NURSE)
        updated = self.client.patch(
            f"/api/admin/v1/hospital-care/staff/{nurse.id}/",
            {"employee_no": "N001", "status": "suspended"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["data"]["employee_no"], "N001")
        self.assertEqual(updated.data["data"]["status"], HospitalStaffMembership.Status.SUSPENDED)

        last_admin = make_staff(hospital, make_user("bo-only-admin"), HospitalStaffMembership.Role.HOSPITAL_ADMIN)
        hospital.status = Hospital.Status.ACTIVE
        hospital.save(update_fields=["status"])
        blocked = self.client.patch(
            f"/api/admin/v1/hospital-care/staff/{last_admin.id}/",
            {"status": "suspended"},
            format="json",
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.data["msg"], "STAFF_LAST_ADMIN")


class BackofficeAgentKnowledgeApiTests(TestCase):
    def setUp(self):
        from ai_config.models import AIModelCatalog

        from hospital_care.tests.factories import make_department, make_doctor, make_embedding_binding, make_provider

        self.client = APIClient()
        self.admin = make_user("bo-agent-admin", is_staff=True, is_superuser=True)
        self.client.force_authenticate(self.admin)
        self.hospital = make_hospital(code="BO-AK")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department, display_name="李医生")
        make_provider()
        AIModelCatalog.objects.get_or_create(
            name="hospital-care-test-model",
            defaults={"display_name": "Test Model", "company": "test", "is_active": True},
        )
        self.embedding = make_embedding_binding()

    def test_create_agent_and_knowledge_flow(self):
        kb = self.client.post(
            f"/api/admin/v1/hospital-care/hospitals/{self.hospital.id}/knowledge-bases/",
            {"name": "就诊须知", "description": "院内文本", "department_ids": [str(self.department.id)]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="kb-1",
        )
        self.assertEqual(kb.status_code, 201, kb.data)
        profile_id = kb.data["data"]["id"]
        replay = self.client.post(
            f"/api/admin/v1/hospital-care/hospitals/{self.hospital.id}/knowledge-bases/",
            {"name": "就诊须知", "description": "院内文本", "department_ids": [str(self.department.id)]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="kb-1",
        )
        self.assertEqual(replay.data["data"]["id"], profile_id)
        conflict = self.client.post(
            f"/api/admin/v1/hospital-care/hospitals/{self.hospital.id}/knowledge-bases/",
            {"name": "另一知识库"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="kb-1",
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["msg"], "IDEMPOTENCY_CONFLICT")

        version = kb.data["data"]["version"]
        doc = self.client.post(
            f"/api/admin/v1/hospital-care/knowledge-bases/{profile_id}/documents/",
            {"title": "挂号须知", "content": "请携带身份证", "version": version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="doc-1",
        )
        self.assertEqual(doc.status_code, 201, doc.data)

        created = self.client.post(
            f"/api/admin/v1/hospital-care/hospitals/{self.hospital.id}/agents/",
            {
                "doctor_id": str(self.doctor.id),
                "department_id": str(self.department.id),
                "name": "李医生 AI 助手",
                "public_summary": "咨询",
                "greeting": "您好",
                "service_boundary": "健康信息与就医指导，不提供确诊。",
                "binding": {"model": "hospital-care-test-model", "temperature": 0.3, "max_tokens": 1024},
                "knowledge_bases": [{"profile_id": profile_id}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="agent-1",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertFalse(created.data["data"]["binding"]["is_default"])
        self.assertEqual(len(created.data["data"]["knowledge_bindings"]), 1)

    def test_permission_denied_without_codes(self):
        staff = make_user("bo-limited", is_staff=True, is_superuser=False)
        self.client.force_authenticate(staff)
        created = self.client.post(
            f"/api/admin/v1/hospital-care/hospitals/{self.hospital.id}/agents/",
            {
                "doctor_id": str(self.doctor.id),
                "department_id": str(self.department.id),
                "name": "无权限助手",
                "binding": {"model": "hospital-care-test-model"},
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="agent-denied",
        )
        self.assertEqual(created.status_code, 403)
        kb = self.client.post(
            f"/api/admin/v1/hospital-care/hospitals/{self.hospital.id}/knowledge-bases/",
            {"name": "无权限库"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="kb-denied",
        )
        self.assertEqual(kb.status_code, 403)
