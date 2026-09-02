from django.test import TestCase

from hospital_care.exceptions import HospitalCareError
from hospital_care.selectors.doctor_workspace import doctor_conversations, get_active_doctor, get_doctor_conversation
from hospital_care.selectors.patient_catalog import get_patient_conversation, patient_conversations, published_agents
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


class SelectorScopeTests(TestCase):
    def setUp(self):
        self.hospital_a = make_hospital(code="HA")
        self.hospital_b = make_hospital(code="HB")
        self.dept_a = make_department(self.hospital_a, code="CA")
        self.dept_b = make_department(self.hospital_b, code="CB")
        self.doctor_a_user = make_user("doc-a")
        self.doctor_b_user = make_user("doc-b")
        self.doctor_a = make_doctor(self.hospital_a, user=self.doctor_a_user, department=self.dept_a, display_name="医生A")
        self.doctor_b = make_doctor(self.hospital_b, user=self.doctor_b_user, department=self.dept_b, display_name="医生B")
        self.agent_a = make_agent(self.hospital_a, self.doctor_a, self.dept_a)
        self.agent_b = make_agent(self.hospital_b, self.doctor_b, self.dept_b)
        self.patient = make_user("pat-a")
        self.member = make_member(self.patient)
        self.binding_a = create_patient_conversation(
            request=DummyRequest(self.patient),
            user=self.patient,
            agent_id=self.agent_a.id,
            member_id=self.member.id,
        )

    def test_patient_catalog_hides_unpublished_and_other_hospital_internals(self):
        self.agent_b.publication_status = self.agent_b.PublicationStatus.DRAFT
        self.agent_b.save(update_fields=["publication_status"])
        names = list(published_agents(hospital_id=self.hospital_a.id).values_list("name", flat=True))
        self.assertIn(self.agent_a.name, names)
        self.assertNotIn(self.agent_b.name, names)

    def test_doctor_cannot_see_other_hospital_conversation(self):
        qs = doctor_conversations(doctor=self.doctor_b)
        self.assertEqual(qs.count(), 0)
        with self.assertRaises(HospitalCareError) as ctx:
            get_doctor_conversation(doctor=self.doctor_b, thread_id=self.binding_a.thread_id)
        self.assertEqual(ctx.exception.error_code, "CONVERSATION_NOT_ASSIGNED")

    def test_other_account_cannot_read_conversation(self):
        stranger = make_user("pat-b")
        make_member(stranger, name="另一人")
        with self.assertRaises(HospitalCareError):
            get_patient_conversation(user=stranger, thread_id=self.binding_a.thread_id)
        self.assertEqual(patient_conversations(user=stranger).count(), 0)

    def test_suspended_staff_cannot_resolve_doctor(self):
        membership = self.doctor_a.staff_membership
        membership.status = membership.Status.SUSPENDED
        membership.save(update_fields=["status"])
        with self.assertRaises(HospitalCareError) as ctx:
            get_active_doctor(user=self.doctor_a_user)
        self.assertEqual(ctx.exception.error_code, "HOSPITAL_MEMBERSHIP_REQUIRED")
