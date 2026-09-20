from django.test import TestCase

from chat_sync.contracts.canonical import KIND_CAPTURE_CARD, KIND_TOOL_QUESTION_CARDS
from chat_sync.models import ChatMessageBlock
from hospital_care.models import ClinicalConversationBinding
from hospital_care.services.conversation_service import create_patient_conversation
from hospital_care.services.doctor_message_service import send_supplementary_report_prompt, send_symptom_collection_prompt
from hospital_care.tests.factories import (
    DummyRequest,
    make_agent,
    make_department,
    make_doctor,
    make_hospital,
    make_member,
    make_user,
)


class SymptomCollectionPromptTests(TestCase):
    def setUp(self):
        self.patient = make_user("symptom-prompt-patient")
        self.member = make_member(self.patient, name="症状患者")
        self.hospital = make_hospital(code="SYMPTOM-PROMPT")
        self.department = make_department(self.hospital)
        self.doctor_user = make_user("symptom-prompt-doctor")
        self.doctor = make_doctor(
            self.hospital,
            user=self.doctor_user,
            department=self.department,
        )
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.binding = create_patient_conversation(
            request=DummyRequest(self.patient),
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
            flow="consultation",
        )
        self.binding.doctor = self.doctor
        self.binding.service_status = ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED
        self.binding.save(update_fields=["doctor", "service_status", "updated_at"])

    def test_doctor_inserts_one_collect_symptoms_starter_card(self):
        result = send_symptom_collection_prompt(
            request=DummyRequest(self.doctor_user),
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            version=self.binding.version,
        )

        block = ChatMessageBlock.objects.get(
            message_id=result["message_id"],
            kind=KIND_TOOL_QUESTION_CARDS,
        )
        cards = block.payload["tool_question_cards"]["_0"]
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card["status"], "pending")
        self.assertEqual(card["prompt"]["tool_name"], "collect_symptoms")
        self.assertEqual(card["prompt"]["questions"][0]["field_key"], "primary_complaint")
        self.assertEqual(card["prompt"]["questions"][0]["options"], [])
        self.assertTrue(card["prompt"]["questions"][0]["allows_other"])

    def test_doctor_inserts_supplementary_report_capture_card(self):
        result = send_supplementary_report_prompt(
            request=DummyRequest(self.doctor_user),
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            version=self.binding.version,
        )

        block = ChatMessageBlock.objects.get(
            message_id=result["message_id"],
            kind=KIND_CAPTURE_CARD,
        )
        card = block.payload["capture_card"]["_0"]
        self.assertEqual(card["card_type"], "supplementary_report")
        self.assertEqual(card["upload_mode"], "inline")
        self.assertEqual(card["status"], "pending")
        self.assertEqual(card["selected_attachments"], [])
        self.assertEqual(block.node_role, "toolPresentation")
