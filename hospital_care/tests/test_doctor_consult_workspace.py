"""DOCTOR-WORKSPACE-000004：线上问诊模块服务端测试。

覆盖：患者发起初始状态、风险调整与历史、已读游标与未读、消息游标分页、
结构化结束原因、医生附件上传与文档消息、重点患者标记、列表搜索/排序/计数。
"""

from __future__ import annotations

import uuid
from io import BytesIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from chat_sync.models import ChatMessage, ChatMessageBlock
from file_manager.models import ManagedFile
from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    ChatMessageAttribution,
    ClinicalConversationBinding,
    Consultation,
    ConversationEndReason,
    DoctorConversationReadCursor,
    DoctorConversationRiskRevision,
    DoctorPatientAttention,
)
from hospital_care.services.conversation_service import (
    create_patient_conversation,
    end_conversation,
    join_conversation,
    update_attention,
    update_risk_level,
)
from hospital_care.services.read_state_service import (
    attachment_count_for_threads,
    mark_conversation_read,
    unread_counts_by_thread,
    unread_totals_by_member,
)
from hospital_care.tests.factories import (
    DummyRequest,
    make_agent,
    make_department,
    make_doctor,
    make_hospital,
    make_member,
    make_user,
)


def _png_bytes(size=(8, 8)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (120, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


class ConsultWorkspaceBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.patient = make_user("dc-patient")
        self.member = make_member(self.patient, name="问诊患者")
        self.hospital = make_hospital(code="DC-H")
        self.department = make_department(self.hospital)
        self.doctor_user = make_user("dc-doc")
        self.doctor = make_doctor(self.hospital, user=self.doctor_user, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.binding = create_patient_conversation(
            request=DummyRequest(self.patient),
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
        )
        self.doctor_request = DummyRequest(self.doctor_user)
        self.client.force_authenticate(self.doctor_user)

    def _patient_message(self, text="头疼两天了") -> ChatMessage:
        from django.utils import timezone

        now = timezone.now()
        message = ChatMessage.objects.create(
            user=self.patient,
            thread=self.binding.thread,
            role=ChatMessage.Role.USER,
            client_message_id=uuid.uuid4(),
            server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=now,
        )
        ChatMessageBlock.objects.create(
            id=uuid.uuid4(),
            user=self.patient,
            thread=self.binding.thread,
            message=message,
            kind="text",
            status=ChatMessageBlock.Status.READY,
            revision=1,
            order_key=1000,
            node_role="timeline",
            payload={"text": {"_0": text}},
            created_at=now,
            updated_at=now,
        )
        ChatMessageAttribution.objects.create(
            message=message,
            actor_type=ChatMessageAttribution.ActorType.PATIENT,
            actor_user=self.patient,
            display_name_snapshot=self.member.name,
            source=ChatMessageAttribution.Source.PATIENT_APP,
        )
        return message

    def _make_pdf_file(self, user) -> ManagedFile:
        record = ManagedFile.objects.create(
            user=user,
            file_uuid=uuid.uuid4(),
            file_path="",
            original_name="报告.pdf",
            file_ext="pdf",
            mime_type="application/pdf",
            file_size=1024,
            file_md5="0" * 32,
            is_public=True,
            object_key=f"zhaodkdream/spark_service/hospital/attachment/{uuid.uuid4().hex}.pdf",
            storage_type="oss",
        )
        from file_manager.business_relations import bind_file_to_business

        bind_file_to_business(user, record, "hospital_conversation", str(self.binding.thread_id))
        return record


class InitialStatusTests(ConsultWorkspaceBase):
    def test_patient_created_conversation_is_pending_doctor(self):
        self.assertEqual(self.binding.service_status, ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR)

    def test_pending_conversation_cannot_send_doctor_message(self):
        response = self.client.post(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/messages/",
            {"text": "你好", "version": self.binding.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="dc-msg-pending",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["msg"], "CONVERSATION_NOT_ASSIGNED")


class RiskUpdateTests(ConsultWorkspaceBase):
    def test_update_risk_writes_revision_and_history(self):
        updated = update_risk_level(
            request=self.doctor_request,
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            payload={"risk_signal_level": "high", "reason": "患者描述胸痛", "version": self.binding.version},
        )
        self.assertEqual(updated.risk_signal_level, "high")
        self.assertEqual(updated.service_status, ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR)

        revision = DoctorConversationRiskRevision.objects.get(binding=self.binding)
        self.assertEqual(revision.previous_level, "none")
        self.assertEqual(revision.next_level, "high")
        self.assertEqual(revision.reason, "患者描述胸痛")
        self.assertEqual(revision.source, "doctor_manual")

        history = self.client.get(f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/risk-history/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data["data"]["current_level"], "high")
        self.assertEqual(len(history.data["data"]["items"]), 1)
        self.assertEqual(history.data["data"]["items"][0]["next_level"], "high")

    def test_update_risk_reason_optional_and_downgrade(self):
        first = update_risk_level(
            request=self.doctor_request,
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            payload={"risk_signal_level": "medium", "version": self.binding.version},
        )
        second = update_risk_level(
            request=self.doctor_request,
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            payload={"risk_signal_level": "none", "version": first.version},
        )
        self.assertEqual(second.risk_signal_level, "none")
        self.assertEqual(DoctorConversationRiskRevision.objects.filter(binding=self.binding).count(), 2)

    def test_update_risk_version_conflict_and_invalid_level(self):
        with self.assertRaises(HospitalCareError) as ctx:
            update_risk_level(
                request=self.doctor_request,
                doctor=self.doctor,
                thread_id=self.binding.thread_id,
                payload={"risk_signal_level": "high", "version": self.binding.version + 5},
            )
        self.assertEqual(ctx.exception.error_code, "CONVERSATION_VERSION_CONFLICT")
        with self.assertRaises(HospitalCareError) as ctx:
            update_risk_level(
                request=self.doctor_request,
                doctor=self.doctor,
                thread_id=self.binding.thread_id,
                payload={"risk_signal_level": "critical", "version": self.binding.version},
            )
        self.assertEqual(ctx.exception.error_code, "PAYLOAD_INVALID")

    def test_update_risk_rejected_after_end(self):
        ended = end_conversation(
            request=self.doctor_request,
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            payload={"version": self.binding.version, "end_reason_code": "resolved"},
        )
        with self.assertRaises(HospitalCareError) as ctx:
            update_risk_level(
                request=self.doctor_request,
                doctor=self.doctor,
                thread_id=self.binding.thread_id,
                payload={"risk_signal_level": "low", "version": ended.version},
            )
        self.assertEqual(ctx.exception.error_code, "CONVERSATION_ENDED")

    def test_other_doctor_cannot_update_risk(self):
        other_user = make_user("dc-doc-other")
        make_doctor(self.hospital, user=other_user, department=self.department, display_name="其他医生")
        self.client.force_authenticate(other_user)
        response = self.client.patch(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/risk/",
            {"risk_signal_level": "high", "version": self.binding.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="dc-risk-other",
        )
        self.assertEqual(response.status_code, 403)


class ReadCursorTests(ConsultWorkspaceBase):
    def test_unread_counts_and_mark_read(self):
        first = self._patient_message("第一条")
        second = self._patient_message("第二条")

        counts = unread_counts_by_thread(doctor=self.doctor, thread_ids=[self.binding.thread_id])
        self.assertEqual(counts[self.binding.thread_id], 2)

        result = mark_conversation_read(
            request=self.doctor_request,
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            last_read_message_id=first.id,
        )
        self.assertEqual(result["last_read_message_id"], first.id)
        self.assertEqual(result["unread_count"], 1)

        # 游标不允许回退
        regressed = mark_conversation_read(
            request=self.doctor_request,
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            last_read_message_id=0,
        )
        self.assertEqual(regressed["last_read_message_id"], first.id)

        # 未指定消息 ID 时标记到最新
        latest = mark_conversation_read(
            request=self.doctor_request,
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
        )
        self.assertEqual(latest["unread_count"], 0)
        self.assertEqual(latest["last_read_message_id"], second.id)

        cursor = DoctorConversationReadCursor.objects.get(doctor=self.doctor, thread_id=self.binding.thread_id)
        self.assertEqual(cursor.last_read_message_id, second.id)

    def test_read_cursor_api(self):
        self._patient_message()
        response = self.client.post(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/read-cursor/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["unread_count"], 0)

    def test_patient_unread_total_excludes_ended(self):
        self._patient_message()
        totals = unread_totals_by_member(doctor=self.doctor)
        self.assertEqual(totals[self.member.id], 1)

        self.binding.service_status = ClinicalConversationBinding.ServiceStatus.ENDED
        self.binding.save(update_fields=["service_status", "updated_at"])
        totals = unread_totals_by_member(doctor=self.doctor)
        self.assertEqual(totals.get(self.member.id, 0), 0)

        # 患者列表卡片附带未读总数
        self.binding.service_status = ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR
        self.binding.save(update_fields=["service_status", "updated_at"])
        response = self.client.get("/api/hospital/v1/doctor/patients/")
        self.assertEqual(response.data["data"]["items"][0]["unread_count"], 1)


class MessagePaginationTests(ConsultWorkspaceBase):
    def test_first_page_latest_and_cursor(self):
        for index in range(35):
            self._patient_message(f"消息 {index}")

        first_page = self.client.get(f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/messages/?limit=30")
        self.assertEqual(first_page.status_code, 200)
        data = first_page.data["data"]
        self.assertEqual(len(data["items"]), 30)
        self.assertTrue(data["has_more"])
        self.assertIsNotNone(data["next_cursor"])
        ids = [item["id"] for item in data["items"]]
        self.assertEqual(ids, sorted(ids))
        # 首屏应为最近一页：包含最后一条消息
        last_message = ChatMessage.objects.filter(thread=self.binding.thread).order_by("-id").first()
        self.assertEqual(ids[-1], last_message.id)

        second_page = self.client.get(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/messages/?limit=30&before={data['next_cursor']}"
        )
        older = second_page.data["data"]
        self.assertFalse(older["has_more"])
        older_ids = [item["id"] for item in older["items"]]
        self.assertEqual(older_ids, sorted(older_ids))
        self.assertTrue(all(item_id < ids[0] for item_id in older_ids))
        self.assertEqual(len(set(ids) & set(older_ids)), 0)

    def test_invalid_before_rejected(self):
        response = self.client.get(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/messages/?before=abc"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "PAYLOAD_INVALID")


class EndReasonTests(ConsultWorkspaceBase):
    def test_end_with_reason_code(self):
        response = self.client.post(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/end/",
            {"version": self.binding.version, "end_reason_code": "offline_referral"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="dc-end-1",
        )
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        self.assertEqual(data["service_status"], "ended")
        self.assertEqual(data["end_reason_code"], "offline_referral")
        self.assertEqual(data["end_reason"], ConversationEndReason.OFFLINE_REFERRAL.label)

        self.binding.refresh_from_db()
        self.assertEqual(self.binding.end_reason_code, "offline_referral")

        # 系统结束提示包含原因摘要
        system_texts = [
            (block.payload or {}).get("text", {}).get("_0", "")
            for block in ChatMessageBlock.objects.filter(thread=self.binding.thread, kind="text")
        ]
        self.assertTrue(any("建议线下就诊" in text for text in system_texts))

    def test_end_other_requires_note(self):
        response = self.client.post(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/end/",
            {"version": self.binding.version, "end_reason_code": "other"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="dc-end-2",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "PAYLOAD_INVALID")

    def test_end_other_with_note(self):
        response = self.client.post(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/end/",
            {"version": self.binding.version, "end_reason_code": "other", "end_reason_note": "患者要求改约"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="dc-end-3",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["end_reason_code"], "other")
        self.assertEqual(response.data["data"]["end_reason_note"], "患者要求改约")

    def test_end_invalid_code_rejected(self):
        response = self.client.post(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/end/",
            {"version": self.binding.version, "end_reason_code": "unknown"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="dc-end-4",
        )
        self.assertEqual(response.status_code, 400)

    def test_end_missing_reason_rejected(self):
        response = self.client.post(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/end/",
            {"version": self.binding.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="dc-end-5",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "PAYLOAD_INVALID")


class AttachmentUploadTests(ConsultWorkspaceBase):
    def _upload(self, content: bytes, name: str, content_type: str, key="dc-upload-1"):
        uploaded = SimpleUploadedFile(name, content, content_type=content_type)
        with mock.patch(
            "hospital_care.services.conversation_attachment_service.put_bytes",
            return_value=mock.Mock(request_id="req-oss"),
        ) as put_mock:
            response = self.client.post(
                f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/attachments/",
                {"file": uploaded},
                format="multipart",
            )
        return response, put_mock

    def test_upload_pdf_success(self):
        response, put_mock = self._upload(_pdf_bytes(), "报告.pdf", "application/pdf")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(put_mock.called)
        data = response.data["data"]
        self.assertEqual(data["mime_type"], "application/pdf")
        self.assertEqual(data["original_name"], "报告.pdf")
        self.assertIn("limits", data)

        record = ManagedFile.objects.get(id=data["file_id"])
        relation = record.business_relations.get()
        self.assertEqual(relation.business_type, "hospital_conversation")
        self.assertEqual(relation.business_id, str(self.binding.thread_id))

    def test_upload_image_success(self):
        response, _ = self._upload(_png_bytes(), "片子.png", "image/png", key="dc-upload-2")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["data"]["mime_type"], "image/png")

    def test_upload_type_unsupported(self):
        response, put_mock = self._upload(b"plain text", "笔记.txt", "text/plain", key="dc-upload-3")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "ATTACHMENT_TYPE_UNSUPPORTED")
        self.assertFalse(put_mock.called)

    def test_upload_fake_pdf_rejected(self):
        response, put_mock = self._upload(b"not a pdf", "伪装.pdf", "application/pdf", key="dc-upload-4")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "ATTACHMENT_TYPE_UNSUPPORTED")
        self.assertFalse(put_mock.called)

    def test_upload_size_limit(self):
        big = b"%PDF-" + b"0" * (20 * 1024 * 1024 + 1)
        response, put_mock = self._upload(big, "大文件.pdf", "application/pdf", key="dc-upload-5")
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.data["msg"], "ATTACHMENT_SIZE_LIMIT")
        self.assertFalse(put_mock.called)

    def test_upload_rejected_after_end(self):
        end_conversation(
            request=self.doctor_request,
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            payload={"version": self.binding.version, "end_reason_code": "resolved"},
        )
        response, put_mock = self._upload(_pdf_bytes(), "报告.pdf", "application/pdf", key="dc-upload-6")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["msg"], "CONVERSATION_ENDED")
        self.assertFalse(put_mock.called)

    def test_doctor_message_with_pdf(self):
        version = join_conversation(
            request=self.doctor_request,
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            version=self.binding.version,
        ).version
        record = self._make_pdf_file(self.doctor_user)
        sent = self.client.post(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/messages/",
            {"text": "请看报告", "version": version, "attachments": [{"file_id": record.id}]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="dc-pdf-msg",
        )
        self.assertEqual(sent.status_code, 200, sent.data)

        messages = self.client.get(f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/messages/")
        doctor_items = [item for item in messages.data["data"]["items"] if item.get("actor_type") == "doctor"]
        self.assertEqual(len(doctor_items), 1)
        kinds = [block["kind"] for block in doctor_items[0]["blocks"]]
        self.assertEqual(kinds, ["text", "fileGallery"])
        gallery = doctor_items[0]["blocks"][1]["payload"]["file_gallery"]["_0"]
        self.assertEqual(gallery[0]["filename"], "报告.pdf")
        self.assertEqual(gallery[0]["mime_type"], "application/pdf")

        counts = attachment_count_for_threads([self.binding.thread_id])
        self.assertEqual(counts[self.binding.thread_id], 1)


class AttentionAndListTests(ConsultWorkspaceBase):
    def test_attention_updates_patient_level_mark(self):
        update_attention(
            request=self.doctor_request,
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            payload={"doctor_attention_level": "priority", "version": self.binding.version},
        )
        mark = DoctorPatientAttention.objects.get(doctor=self.doctor, member_id=self.member.id)
        self.assertEqual(mark.level, "priority")

        response = self.client.get("/api/hospital/v1/doctor/patients/?queue=priority")
        self.assertEqual(response.data["data"]["pagination"]["total"], 1)
        self.assertTrue(response.data["data"]["items"][0]["priority_patient"])

    def test_patient_list_active_queue(self):
        join_conversation(
            request=self.doctor_request,
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            version=self.binding.version,
        )
        response = self.client.get("/api/hospital/v1/doctor/patients/?queue=active")
        self.assertEqual(response.data["data"]["pagination"]["total"], 1)
        self.assertEqual(response.data["data"]["counts"]["active"], 1)

    def test_conversation_list_unread_and_keyword(self):
        self._patient_message("患者补充")
        listing = self.client.get("/api/hospital/v1/doctor/conversations/")
        item = listing.data["data"]["items"][0]
        self.assertEqual(item["unread_count"], 1)
        self.assertEqual(item["attachment_count"], 0)

        # 按患者姓名搜索
        by_name = self.client.get("/api/hospital/v1/doctor/conversations/?keyword=问诊患者")
        self.assertEqual(by_name.data["data"]["pagination"]["total"], 1)
        # 按患者编号搜索
        by_number = self.client.get(f"/api/hospital/v1/doctor/conversations/?keyword=P{self.member.id:010d}")
        self.assertEqual(by_number.data["data"]["pagination"]["total"], 1)
        # 不命中
        miss = self.client.get("/api/hospital/v1/doctor/conversations/?keyword=无关关键词")
        self.assertEqual(miss.data["data"]["pagination"]["total"], 0)

    def test_patient_conversations_include_unread_and_attachments(self):
        self._patient_message("医生您好，最近胸口闷")
        response = self.client.get(f"/api/hospital/v1/doctor/patients/{self.member.id}/conversations/")
        item = response.data["data"]["items"][0]
        self.assertEqual(item["unread_count"], 1)
        self.assertEqual(item["attachment_count"], 0)
        self.assertEqual(item["first_patient_message_excerpt"], "医生您好，最近胸口闷")
        self.assertFalse(item["doctor_replied"])

    def test_conversation_activity_doctor_replied(self):
        self._patient_message()
        joined = join_conversation(
            request=self.doctor_request,
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            version=self.binding.version,
        )
        self.client.post(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/messages/",
            {"text": "请注意休息", "version": joined.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="dc-replied-msg",
        )
        response = self.client.get(f"/api/hospital/v1/doctor/patients/{self.member.id}/conversations/")
        self.assertTrue(response.data["data"]["items"][0]["doctor_replied"])

    def test_conversation_attachments_list(self):
        version = join_conversation(
            request=self.doctor_request,
            doctor=self.doctor,
            thread_id=self.binding.thread_id,
            version=self.binding.version,
        ).version
        record = self._make_pdf_file(self.doctor_user)
        sent = self.client.post(
            f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/messages/",
            {"text": "", "version": version, "attachments": [{"file_id": record.id}]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="dc-pdf-only-msg",
        )
        self.assertEqual(sent.status_code, 200, sent.data)

        listing = self.client.get(f"/api/hospital/v1/doctor/conversations/{self.binding.thread_id}/attachments/")
        self.assertEqual(listing.status_code, 200)
        items = listing.data["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["filename"], "报告.pdf")
        self.assertEqual(items[0]["kind"], "document")
        self.assertEqual(items[0]["mime_type"], "application/pdf")


class ConsultationSubmitTests(ConsultWorkspaceBase):
    """DOCTOR-WORKSPACE-000004 页面形态修订：独立问诊单提交与问诊工作台列表。"""

    def setUp(self):
        super().setUp()
        self.patient_client = APIClient()
        self.patient_client.force_authenticate(self.patient)

    def _submit(self, complaint="最近胸口闷，爬楼梯时心慌", **extra):
        payload = {"agent_id": str(self.agent.id), "member_id": self.member.id, "chief_complaint": complaint}
        payload.update(extra)
        return self.patient_client.post(
            "/api/v1/hospital-care/consultations/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=extra.get("idempotency_key", f"dc-consult-{uuid.uuid4().hex[:8]}"),
        )

    def test_submit_consultation_creates_record_with_consult_no(self):
        response = self._submit()
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data["data"]
        self.assertTrue(data["consult_no"].startswith("C"))
        self.assertEqual(len(data["consult_no"]), 13)
        self.assertEqual(data["chief_complaint"], "最近胸口闷，爬楼梯时心慌")
        self.assertEqual(data["service_status"], ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR)

        consultation = Consultation.objects.get(consult_no=data["consult_no"])
        self.assertEqual(consultation.member_id, self.member.id)
        self.assertEqual(str(consultation.binding.thread_id), data["thread_id"])

        # 首条患者消息为线上问诊消息卡片，归属患者端。
        first = (
            ChatMessage.objects.filter(thread=consultation.binding.thread, role=ChatMessage.Role.USER)
            .order_by("created_at", "id")
            .first()
        )
        self.assertIsNotNone(first)
        block = first.blocks.filter(kind="consultationCard").first()
        self.assertIsNotNone(block)
        card = block.payload["consultation_card"]["_0"]
        self.assertEqual(card["chief_complaint"], "最近胸口闷，爬楼梯时心慌")
        self.assertEqual(card["consult_no"], data["consult_no"])
        self.assertEqual(card["attachments"], [])
        self.assertEqual(first.hospital_attribution.actor_type, ChatMessageAttribution.ActorType.PATIENT)

    def test_submit_consultation_is_idempotent_by_thread_id(self):
        first = self._submit(thread_id=uuid.uuid4())
        self.assertEqual(first.status_code, 201, first.data)
        thread_id = first.data["data"]["thread_id"]
        replay = self._submit(thread_id=thread_id)
        self.assertEqual(replay.status_code, 201, replay.data)
        self.assertEqual(replay.data["data"]["consult_no"], first.data["data"]["consult_no"])
        self.assertEqual(Consultation.objects.filter(member_id=self.member.id).count(), 1)

    def test_submit_consultation_requires_complaint(self):
        response = self._submit(complaint="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "PAYLOAD_INVALID")

    def test_patient_consultation_list(self):
        created = self._submit()
        self.assertEqual(created.status_code, 201, created.data)
        listing = self.patient_client.get(f"/api/v1/hospital-care/consultations/?member_id={self.member.id}")
        self.assertEqual(listing.status_code, 200)
        items = listing.data["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["consult_no"], created.data["data"]["consult_no"])

    def test_submit_consultation_stores_material_and_returns_card_fields(self):
        record = self._make_pdf_file(self.patient)
        response = self._submit(
            attachments=[{"file_id": record.id}],
            order_items=["复诊开药", "开具检查"],
            past_history="高血压三年",
            family_history="父亲有冠心病",
            allergy_history="青霉素过敏",
        )
        self.assertEqual(response.status_code, 201, response.data)
        consultation = Consultation.objects.get(consult_no=response.data["data"]["consult_no"])
        self.assertEqual(consultation.order_items, ["复诊开药", "开具检查"])
        self.assertEqual(consultation.past_history, "高血压三年")
        self.assertEqual(consultation.family_history, "父亲有冠心病")
        self.assertEqual(consultation.allergy_history, "青霉素过敏")

        listing = self.patient_client.get(f"/api/v1/hospital-care/consultations/?member_id={self.member.id}")
        item = listing.data["data"]["items"][0]
        self.assertEqual(item["doctor"]["display_name"], "张医生")
        self.assertEqual(item["department"]["name"], self.department.name)
        self.assertEqual(item["hospital"]["name"], self.hospital.name)
        self.assertEqual(item["order_items"], ["复诊开药", "开具检查"])
        self.assertEqual(item["allergy_history"], "青霉素过敏")
        self.assertEqual(item["attachment_count"], 1)

        first = (
            ChatMessage.objects.filter(thread=consultation.binding.thread, role=ChatMessage.Role.USER)
            .order_by("created_at", "id")
            .first()
        )
        card = first.blocks.filter(kind="consultationCard").first()
        attachments = card.payload["consultation_card"]["_0"]["attachments"]
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]["type"], "document")
        self.assertEqual(attachments[0]["file_id"], record.id)
        self.assertTrue(attachments[0]["url"])
        self.assertTrue(attachments[0]["filename"])

    def test_consult_patient_list_only_includes_submitted_patients(self):
        # setUp 中已有一条普通会话（非问诊单）；问诊列表不应包含该患者。
        listing = self.client.get("/api/hospital/v1/doctor/consults/patients/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["data"]["pagination"]["total"], 0)
        self.assertEqual(listing.data["data"]["counts"]["all"], 0)

        # 患者工作台患者列表不受问诊单影响，仍包含普通会话患者。
        workspace = self.client.get("/api/hospital/v1/doctor/patients/")
        self.assertEqual(workspace.data["data"]["pagination"]["total"], 1)

        # 提交线上问诊后进入问诊列表。
        created = self._submit()
        self.assertEqual(created.status_code, 201, created.data)
        listing = self.client.get("/api/hospital/v1/doctor/consults/patients/")
        self.assertEqual(listing.data["data"]["pagination"]["total"], 1)
        item = listing.data["data"]["items"][0]
        self.assertEqual(item["member_id"], self.member.id)
        self.assertEqual(item["service_status"], ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR)
        self.assertEqual(item["available_conversation_count"], 1)
        counts = listing.data["data"]["counts"]
        self.assertEqual(counts["all"], 1)
        self.assertEqual(counts["pending"], 1)

    def test_consult_records_include_consult_no_and_complaint(self):
        created = self._submit()
        self.assertEqual(created.status_code, 201, created.data)
        records = self.client.get(f"/api/hospital/v1/doctor/consults/patients/{self.member.id}/records/")
        self.assertEqual(records.status_code, 200)
        items = records.data["data"]["items"]
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["consult_no"], created.data["data"]["consult_no"])
        self.assertEqual(item["chief_complaint"], "最近胸口闷，爬楼梯时心慌")
        self.assertEqual(item["first_patient_message_excerpt"], "最近胸口闷，爬楼梯时心慌")
        self.assertFalse(item["doctor_replied"])
        self.assertIsNotNone(item["submitted_at"])

    def test_consult_records_exclude_plain_conversations(self):
        # 未提交问诊时：普通会话不出现在问诊记录中。
        records = self.client.get(f"/api/hospital/v1/doctor/consults/patients/{self.member.id}/records/")
        self.assertEqual(records.status_code, 200)
        self.assertEqual(records.data["data"]["items"], [])

    def test_submit_consultation_exposes_consultation_ref_and_doctor_only_disclaimer(self):
        """问诊会话必须带 consultation 标识，开场文案不得写成医生智能体。"""
        created = self._submit()
        self.assertEqual(created.status_code, 201, created.data)
        thread_id = created.data["data"]["thread_id"]
        consult_no = created.data["data"]["consult_no"]

        listing = self.patient_client.get(f"/api/v1/hospital-care/conversations/?member_id={self.member.id}")
        self.assertEqual(listing.status_code, 200)
        items = listing.data["data"]["items"]
        consult_item = next(item for item in items if item["thread_id"] == thread_id)
        self.assertEqual(consult_item["consultation"]["consultation_id"], created.data["data"]["consultation_id"])
        self.assertEqual(consult_item["consultation"]["consult_no"], consult_no)

        context = self.patient_client.get(f"/api/v1/hospital-care/conversations/{thread_id}/context/")
        self.assertEqual(context.status_code, 200)
        self.assertEqual(context.data["data"]["consultation"]["consult_no"], consult_no)

        texts = [
            block.payload.get("text", {}).get("_0", "")
            for block in ChatMessageBlock.objects.filter(thread_id=thread_id, kind="text")
        ]
        joined = "\n".join(texts)
        self.assertIn("线上问诊", joined)
        self.assertNotIn("智能体", joined)
        self.assertNotIn("本助手", joined)
        self.assertNotIn("AI", joined)
