from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from chat_sync.contracts.canonical import KIND_HOSPITAL_DOCTOR_INTRO_CARD, payload_kind
from chat_sync.models import ChatMessage, ChatMessageBlock
from chat_sync.views import _to_payload, _to_thread_payload
from file_manager.models import ManagedFile
from hospital_care.api.presenters import conversation_create_snapshot, conversation_public, doctor_public
from hospital_care.selectors.patient_catalog import latest_conversation_for_agent, published_agents
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


class PublishedAgentDedupTests(TestCase):
    def setUp(self):
        self.hospital = make_hospital(code="DEDUP-H")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department, display_name="张医生")

    def test_returns_latest_published_agent_per_doctor(self):
        older = make_agent(self.hospital, self.doctor, self.department)
        older.published_at = timezone.now() - timedelta(days=2)
        older.name = "张医生旧助手"
        older.save(update_fields=["published_at", "name"])
        newer = make_agent(self.hospital, self.doctor, self.department)
        newer.published_at = timezone.now()
        newer.name = "张医生新助手"
        newer.save(update_fields=["published_at", "name"])

        ids = list(published_agents(hospital_id=self.hospital.id).values_list("id", flat=True))
        self.assertEqual(ids, [newer.id])

    def test_keyword_matches_doctor_title_and_department(self):
        make_agent(self.hospital, self.doctor, self.department)
        by_title = published_agents(hospital_id=self.hospital.id, keyword="主任医师")
        by_dept = published_agents(hospital_id=self.hospital.id, keyword="心内科")
        by_name = published_agents(hospital_id=self.hospital.id, keyword="张医生")
        self.assertEqual(by_title.count(), 1)
        self.assertEqual(by_dept.count(), 1)
        self.assertEqual(by_name.count(), 1)
        self.assertEqual(published_agents(hospital_id=self.hospital.id, keyword="皮肤科").count(), 0)


class DoctorPublicPresenterTests(TestCase):
    def test_avatar_url_empty_without_file(self):
        hospital = make_hospital(code="AVATAR-H")
        doctor = make_doctor(hospital, display_name="无头像医生")
        payload = doctor_public(doctor)
        self.assertEqual(payload["avatar_url"], "")
        self.assertEqual(payload["display_name"], "无头像医生")

    def test_avatar_url_uses_public_file_path(self):
        hospital = make_hospital(code="AVATAR-H2")
        doctor = make_doctor(hospital, display_name="有头像医生")
        owner = doctor.staff_membership.user
        avatar = ManagedFile.objects.create(
            user=owner,
            file_path="https://cdn.example.test/doctors/zhang.png",
            original_name="zhang.png",
            file_ext="png",
            mime_type="image/png",
        )
        doctor.avatar_file = avatar
        doctor.save(update_fields=["avatar_file"])
        payload = doctor_public(doctor)
        self.assertEqual(payload["avatar_url"], "https://cdn.example.test/doctors/zhang.png")


class DoctorIntroCardTests(TestCase):
    def setUp(self):
        self.patient = make_user("intro-patient")
        self.member = make_member(self.patient)
        self.hospital = make_hospital(code="INTRO-H")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department, display_name="李医生")
        self.doctor.specialties = ["胸痛评估", "高血压管理", "心律失常", "额外方向"]
        self.doctor.introduction = "从事心血管内科临床工作多年，擅长胸痛与高血压管理。"
        self.doctor.save(update_fields=["specialties", "introduction"])
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.request = DummyRequest(self.patient)

    def test_create_conversation_inserts_intro_card_then_disclaimer(self):
        binding = create_patient_conversation(
            request=self.request,
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
        )
        blocks = list(ChatMessageBlock.objects.filter(thread=binding.thread).order_by("created_at", "id"))
        kinds = [block.kind for block in blocks]
        self.assertIn(KIND_HOSPITAL_DOCTOR_INTRO_CARD, kinds)
        self.assertEqual(kinds.count(KIND_HOSPITAL_DOCTOR_INTRO_CARD), 1)
        self.assertEqual(kinds[0], KIND_HOSPITAL_DOCTOR_INTRO_CARD)
        self.assertIn("text", kinds)

        intro = blocks[0]
        self.assertEqual(payload_kind(intro.payload), KIND_HOSPITAL_DOCTOR_INTRO_CARD)
        snapshot = intro.payload["hospital_doctor_intro_card"]["_0"]
        self.assertEqual(snapshot["doctor"]["display_name"], "李医生")
        self.assertEqual(snapshot["doctor"]["department_name"], "心内科")
        self.assertEqual(snapshot["agent"]["agent_id"], str(self.agent.id))
        self.assertEqual(snapshot["professional_directions"], ["胸痛评估", "高血压管理", "心律失常"])
        self.assertTrue(snapshot["introduction_excerpt"].startswith("从事心血管内科"))
        self.assertEqual(snapshot["detail_route"]["agent_id"], str(self.agent.id))

        latest = latest_conversation_for_agent(
            user=self.patient,
            member_id=self.member.id,
            agent_id=self.agent.id,
        )
        self.assertEqual(latest.thread_id, binding.thread_id)

    def test_intro_card_idempotent_on_existing_thread(self):
        first = create_patient_conversation(
            request=self.request,
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
            thread_id=None,
        )
        replay = create_patient_conversation(
            request=self.request,
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
            thread_id=first.thread_id,
        )
        self.assertEqual(replay.thread_id, first.thread_id)
        self.assertEqual(
            ChatMessageBlock.objects.filter(thread=first.thread, kind=KIND_HOSPITAL_DOCTOR_INTRO_CARD).count(),
            1,
        )

    def test_create_snapshot_returns_canonical_thread_and_initial_messages(self):
        binding = create_patient_conversation(
            request=self.request,
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
        )
        snapshot = conversation_create_snapshot(binding)
        self.assertEqual(snapshot["thread_id"], str(binding.thread_id))
        self.assertEqual(snapshot["thread"], _to_thread_payload(binding.thread))
        self.assertEqual(snapshot["conversation"]["thread_id"], str(binding.thread_id))

        messages = list(
            ChatMessage.objects.filter(thread=binding.thread)
            .prefetch_related("blocks", "hospital_attribution")
            .order_by("created_at", "id")
        )
        self.assertEqual(len(snapshot["initial_messages"]), 2)
        self.assertEqual(len(messages), 2)
        kinds = [block["kind"] for item in snapshot["initial_messages"] for block in item["blocks"]]
        self.assertEqual(kinds[0], KIND_HOSPITAL_DOCTOR_INTRO_CARD)
        self.assertIn("text", kinds)
        self.assertEqual(snapshot["initial_messages"][0]["client_message_id"], str(messages[0].client_message_id))
        self.assertEqual(snapshot["initial_messages"][0]["server_message_id"], messages[0].server_message_id)
        self.assertEqual(snapshot["initial_messages"][0]["thread_id"], str(binding.thread_id))
        self.assertEqual(snapshot["initial_messages"][0]["blocks"][0]["id"], str(messages[0].blocks.first().id))
        for message, payload in zip(messages, snapshot["initial_messages"]):
            expected = _to_payload(message)
            self.assertEqual(payload["client_message_id"], expected["client_message_id"])
            self.assertEqual(payload["server_message_id"], expected["server_message_id"])
            self.assertEqual(payload["blocks"][0]["id"], expected["blocks"][0]["id"])
            self.assertEqual(payload["blocks"][0]["kind"], expected["blocks"][0]["kind"])

        replay = conversation_create_snapshot(binding)
        self.assertEqual(
            [item["server_message_id"] for item in replay["initial_messages"]],
            [item["server_message_id"] for item in snapshot["initial_messages"]],
        )
        self.assertEqual(
            ChatMessageBlock.objects.filter(thread=binding.thread, kind=KIND_HOSPITAL_DOCTOR_INTRO_CARD).count(),
            1,
        )
        self.assertIsNone(conversation_public(binding)["consultation"])

    def test_consultation_flow_disclaimer_omits_agent_wording(self):
        binding = create_patient_conversation(
            request=self.request,
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
            flow="consultation",
        )
        texts = [
            block.payload.get("text", {}).get("_0", "")
            for block in ChatMessageBlock.objects.filter(thread=binding.thread, kind="text")
        ]
        joined = "\n".join(texts)
        self.assertIn("线上问诊", joined)
        self.assertNotIn("智能体", joined)
        self.assertNotIn("本助手", joined)
        self.assertNotIn("AI", joined)
        self.assertIsNone(conversation_public(binding)["consultation"])
