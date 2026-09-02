from django.test import TestCase

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import ClinicalConversationBinding, DoctorProfile, Hospital, HospitalStaffMembership
from hospital_care.services.conversation_service import create_patient_conversation, end_conversation, join_conversation
from hospital_care.services.doctor_message_service import send_doctor_message
from hospital_care.services.hospital_admin_service import activate_hospital, create_hospital, suspend_hospital, update_staff
from hospital_care.services.idempotency import CommandIdempotency, request_hash
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


class HospitalStateMachineTests(TestCase):
    def setUp(self):
        self.admin = make_user("svc-admin", is_staff=True)
        self.request = DummyRequest(self.admin)

    def test_activate_requires_admin_and_complete_fields(self):
        hospital = create_hospital(
            request=self.request,
            payload={
                "code": "ACT-1",
                "name": "启用医院",
                "province_code": "340000",
                "city_code": "341100",
                "address": "路 1 号",
                "service_mode": Hospital.ServiceMode.DEMO,
            },
        )
        with self.assertRaises(HospitalCareError) as ctx:
            activate_hospital(request=self.request, hospital_id=hospital.id, version=hospital.version)
        self.assertEqual(ctx.exception.error_code, "HOSPITAL_ACTIVATE_INVALID")

        make_staff(hospital, self.admin, HospitalStaffMembership.Role.HOSPITAL_ADMIN)
        hospital.refresh_from_db()
        activated = activate_hospital(request=self.request, hospital_id=hospital.id, version=hospital.version)
        self.assertEqual(activated.status, Hospital.Status.ACTIVE)

    def test_version_conflict(self):
        hospital = make_hospital(code="VER-1", status=Hospital.Status.ACTIVE)
        make_staff(hospital, self.admin, HospitalStaffMembership.Role.HOSPITAL_ADMIN)
        with self.assertRaises(HospitalCareError) as ctx:
            suspend_hospital(request=self.request, hospital_id=hospital.id, version=hospital.version + 9, reason="测试")
        self.assertEqual(ctx.exception.error_code, "HOSPITAL_VERSION_CONFLICT")

    def test_suspend_then_reactivate(self):
        hospital = make_hospital(code="VER-2", status=Hospital.Status.ACTIVE)
        make_staff(hospital, self.admin, HospitalStaffMembership.Role.HOSPITAL_ADMIN)
        suspended = suspend_hospital(request=self.request, hospital_id=hospital.id, version=hospital.version, reason="维护")
        self.assertEqual(suspended.status, Hospital.Status.SUSPENDED)
        activated = activate_hospital(request=self.request, hospital_id=hospital.id, version=suspended.version)
        self.assertEqual(activated.status, Hospital.Status.ACTIVE)

    def test_update_staff_promotes_to_doctor_and_locks_role(self):
        hospital = make_hospital(code="STAFF-1")
        nurse_user = make_user("svc-nurse")
        nurse = make_staff(hospital, nurse_user, HospitalStaffMembership.Role.NURSE)
        updated = update_staff(
            request=self.request,
            staff_id=nurse.id,
            payload={"role": HospitalStaffMembership.Role.DOCTOR, "employee_no": "D100", "display_name": "护士转医生"},
        )
        self.assertEqual(updated.role, HospitalStaffMembership.Role.DOCTOR)
        self.assertEqual(updated.employee_no, "D100")
        self.assertTrue(DoctorProfile.objects.filter(staff_membership=updated, display_name="护士转医生").exists())
        with self.assertRaises(HospitalCareError) as ctx:
            update_staff(
                request=self.request,
                staff_id=updated.id,
                payload={"role": HospitalStaffMembership.Role.NURSE},
            )
        self.assertEqual(ctx.exception.error_code, "STAFF_ROLE_LOCKED")


class ConversationServiceTests(TestCase):
    def setUp(self):
        self.patient = make_user("svc-patient")
        self.member = make_member(self.patient)
        self.hospital = make_hospital(code="CONV-1")
        self.department = make_department(self.hospital)
        self.doctor_user = make_user("svc-doctor")
        self.doctor = make_doctor(self.hospital, user=self.doctor_user, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.request = DummyRequest(self.patient)

    def test_create_and_doctor_flow(self):
        binding = create_patient_conversation(
            request=self.request,
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
        )
        self.assertEqual(binding.service_status, ClinicalConversationBinding.ServiceStatus.AI_ACTIVE)
        self.assertEqual(binding.thread.member_id, self.member.id)

        doctor_request = DummyRequest(self.doctor_user)
        joined = join_conversation(request=doctor_request, doctor=self.doctor, thread_id=binding.thread_id, version=binding.version)
        self.assertEqual(joined.service_status, ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED)

        payload = send_doctor_message(
            request=doctor_request,
            doctor=self.doctor,
            thread_id=joined.thread_id,
            text="请立即就医",
            version=joined.version,
        )
        self.assertEqual(payload["sender"]["actor_type"], "doctor")
        self.assertEqual(payload["role"], "assistant")

        ended = end_conversation(
            request=doctor_request,
            doctor=self.doctor,
            thread_id=joined.thread_id,
            payload={"version": payload["version"], "end_reason": "已完成咨询"},
        )
        self.assertEqual(ended.service_status, ClinicalConversationBinding.ServiceStatus.ENDED)
        with self.assertRaises(HospitalCareError) as ctx:
            send_doctor_message(request=doctor_request, doctor=self.doctor, thread_id=ended.thread_id, text="再发一条", version=ended.version)
        self.assertEqual(ctx.exception.error_code, "CONVERSATION_ENDED")

    def test_suspended_hospital_cannot_create_conversation(self):
        self.hospital.status = Hospital.Status.SUSPENDED
        self.hospital.save(update_fields=["status"])
        with self.assertRaises(HospitalCareError) as ctx:
            create_patient_conversation(
                request=self.request,
                user=self.patient,
                agent_id=self.agent.id,
                member_id=self.member.id,
            )
        self.assertEqual(ctx.exception.error_code, "HOSPITAL_INACTIVE")

    def test_unpublished_agent_rejected(self):
        self.agent.publication_status = self.agent.PublicationStatus.DRAFT
        self.agent.save(update_fields=["publication_status"])
        with self.assertRaises(HospitalCareError) as ctx:
            create_patient_conversation(
                request=self.request,
                user=self.patient,
                agent_id=self.agent.id,
                member_id=self.member.id,
            )
        self.assertEqual(ctx.exception.error_code, "AGENT_NOT_PUBLISHED")

    def test_illegal_member_denied(self):
        stranger = make_user("svc-stranger")
        stranger_member = make_member(stranger, name="外人")
        with self.assertRaises(HospitalCareError) as ctx:
            create_patient_conversation(
                request=self.request,
                user=self.patient,
                agent_id=self.agent.id,
                member_id=stranger_member.id,
            )
        self.assertEqual(ctx.exception.error_code, "MEMBER_ACCESS_DENIED")


class IdempotencyTests(TestCase):
    def test_same_key_different_hash_conflicts(self):
        user = make_user("idemp")
        CommandIdempotency.record(
            user=user,
            key="k1",
            request_hash_value=request_hash({"a": 1}),
            resource_type="hospital",
            resource_id="1",
            response_code=0,
            response_snapshot={"ok": True},
        )
        with self.assertRaises(HospitalCareError) as ctx:
            CommandIdempotency.lookup(user=user, key="k1", request_hash_value=request_hash({"a": 2}))
        self.assertEqual(ctx.exception.error_code, "IDEMPOTENCY_CONFLICT")

    def test_same_key_same_hash_returns_receipt(self):
        user = make_user("idemp2")
        digest = request_hash({"a": 1})
        CommandIdempotency.record(
            user=user,
            key="k2",
            request_hash_value=digest,
            resource_type="hospital",
            resource_id="1",
            response_code=0,
            response_snapshot={"ok": True},
        )
        receipt = CommandIdempotency.lookup(user=user, key="k2", request_hash_value=digest)
        self.assertEqual(receipt.response_snapshot, {"ok": True})
