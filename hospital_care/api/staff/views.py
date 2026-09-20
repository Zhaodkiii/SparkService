import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.views import APIView

from accounts.services.web_session_service import WebSessionService
from backoffice.models import AdminAuditLog
from chat_sync.ai_models import ChatWebSocketTicket
from chat_sync.models import ChatMessage
from common.response import success_response
from hospital_care.api.pagination import paginate_queryset
from hospital_care.exceptions import HospitalCareError
from hospital_care.api.presenters import agent_public, conversation_public, serialize_message, staff_me
from hospital_care.api.staff.serializers import (
    ConversationEndSerializer,
    ConversationVersionSerializer,
    DoctorAgentSubmitSerializer,
    DoctorAgentUpdateSerializer,
    DoctorMessageSerializer,
    ReadCursorUpdateSerializer,
    SupplementaryReportCreateSerializer,
    SymptomCollectionCreateSerializer,
)
from hospital_care.permissions import DoctorConversationPermission, HospitalStaffPermission
from hospital_care.realtime import DOCTOR_CONVERSATION_WS_PATH
from hospital_care.selectors.doctor_workspace import doctor_agent, doctor_conversations, doctor_queue_counts, get_doctor_conversation
from hospital_care.selectors.patient_workspace import doctor_patient_agent_conversations
from hospital_care.services.agent_service import submit_agent_for_review, upsert_doctor_agent
from hospital_care.services.audit import write_hospital_audit_log
from hospital_care.services.conversation_attachment_service import (
    attachment_limits,
    list_conversation_attachments,
    upload_conversation_attachment,
)
from hospital_care.services.consultation_service import build_consult_patient_list, doctor_member_consultations
from hospital_care.services.conversation_service import (
    end_conversation,
    join_conversation,
    leave_conversation,
)
from hospital_care.services.doctor_message_service import (
    send_doctor_message,
    send_supplementary_report_prompt,
    send_symptom_collection_prompt,
)
from hospital_care.services.idempotency import run_idempotent_command
from hospital_care.services.patient_workspace_service import (
    build_patient_list,
    build_patient_workspace,
    create_doctor_patient_conversation,
)
from hospital_care.services.read_state_service import (
    attachment_count_for_threads,
    conversation_activity_summaries,
    mark_conversation_read,
    unread_counts_by_thread,
)


class StaffMeView(APIView):
    permission_classes = [HospitalStaffPermission]

    def get(self, request):
        return success_response(staff_me(request.hospital_membership))


class StaffAgentView(APIView):
    permission_classes = [DoctorConversationPermission]

    def get(self, request):
        agent = doctor_agent(doctor=request.hospital_doctor)
        if agent is None:
            return success_response(None)
        return success_response(agent_public(agent, include_internal=True))

    def patch(self, request):
        serializer = DoctorAgentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agent = upsert_doctor_agent(request=request, doctor=request.hospital_doctor, payload=serializer.validated_data)
        return success_response(agent_public(agent, include_internal=True))


class StaffAgentSubmitView(APIView):
    permission_classes = [DoctorConversationPermission]

    def post(self, request):
        serializer = DoctorAgentSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agent = submit_agent_for_review(
            request=request,
            doctor=request.hospital_doctor,
            version=serializer.validated_data["version"],
        )
        return success_response(agent_public(agent, include_internal=True))


class DoctorWorkspaceView(APIView):
    permission_classes = [DoctorConversationPermission]

    def get(self, request):
        doctor = request.hospital_doctor
        counts = doctor_queue_counts(doctor=doctor)
        return success_response(
            {
                "doctor": {
                    "id": str(doctor.id),
                    "display_name": doctor.display_name,
                    "title": doctor.title,
                },
                "hospital": {
                    "id": str(doctor.staff_membership.hospital_id),
                    "name": doctor.staff_membership.hospital.name,
                },
                "counts": counts,
            }
        )


class DoctorConversationListView(APIView):
    permission_classes = [DoctorConversationPermission]

    def get(self, request):
        doctor = request.hospital_doctor
        qs = doctor_conversations(
            doctor=doctor,
            queue=(request.query_params.get("queue") or "all").strip(),
            keyword=(request.query_params.get("keyword") or "").strip(),
        )
        page_obj, pagination = paginate_queryset(qs, request)
        thread_ids = [item.thread_id for item in page_obj.object_list]
        unread_map = unread_counts_by_thread(doctor=doctor, thread_ids=thread_ids)
        attachment_map = attachment_count_for_threads(thread_ids)
        return success_response(
            {
                "items": [
                    conversation_public(
                        item,
                        for_doctor=True,
                        unread_count=unread_map.get(item.thread_id, 0),
                        attachment_count=attachment_map.get(item.thread_id, 0),
                    )
                    for item in page_obj.object_list
                ],
                "pagination": pagination,
                "counts": doctor_queue_counts(doctor=doctor),
            }
        )


class DoctorConversationDetailView(APIView):
    permission_classes = [DoctorConversationPermission]

    def get(self, request, thread_id):
        doctor = request.hospital_doctor
        binding = get_doctor_conversation(doctor=doctor, thread_id=thread_id)
        unread_map = unread_counts_by_thread(doctor=doctor, thread_ids=[binding.thread_id])
        attachment_map = attachment_count_for_threads([binding.thread_id])
        payload = conversation_public(
            binding,
            for_doctor=True,
            unread_count=unread_map.get(binding.thread_id, 0),
            attachment_count=attachment_map.get(binding.thread_id, 0),
        )
        # 独立问诊单关联信息（线上问诊工作台展示问诊编号与主诉）。
        consultation = getattr(binding, "consultation", None)
        if consultation is not None:
            payload["consult_no"] = consultation.consult_no
            payload["chief_complaint"] = consultation.chief_complaint
            payload["submitted_at"] = consultation.submitted_at.isoformat() if consultation.submitted_at else None
        return success_response(payload)


class DoctorConversationWebSocketTicketView(APIView):
    """BACKOFFICE-CONVERSATION-000002：医生工作台实时通道一次性 ticket。

    与医生消息 REST 共用 DoctorConversationPermission；ticket 绑定医生实时
    WebSocket 路径、短 TTL、单次消费，不携带 thread_id 或任何会话数据。
    """

    permission_classes = [DoctorConversationPermission]

    def post(self, request):
        ttl = max(5, min(120, int(getattr(settings, "HOSPITAL_DOCTOR_WS_TICKET_TTL_SECONDS", 30))))
        raw_ticket = secrets.token_urlsafe(32)
        now = timezone.now()
        claims = dict(getattr(request.auth, "payload", {}) or {})
        web_session_id = None
        web_session_version = None
        if WebSessionService.claims_require_web_session(claims):
            web_session_id = claims.get("web_session_id")
            web_session_version = int(claims.get("web_session_version") or 0) or None
        ChatWebSocketTicket.objects.create(
            user=request.user,
            web_session_id=web_session_id,
            web_session_version=web_session_version,
            token_hash=hashlib.sha256(raw_ticket.encode("utf-8")).hexdigest(),
            websocket_path=DOCTOR_CONVERSATION_WS_PATH,
            expires_at=now + timedelta(seconds=ttl),
        )
        ChatWebSocketTicket.objects.filter(expires_at__lt=now - timedelta(minutes=5)).delete()
        return success_response(
            {"ticket": raw_ticket, "expires_in": ttl, "websocket_path": DOCTOR_CONVERSATION_WS_PATH},
            msg="created",
            status_code=201,
        )


class DoctorSymptomCollectionView(APIView):
    permission_classes = [DoctorConversationPermission]

    def post(self, request, thread_id):
        serializer = SymptomCollectionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = send_symptom_collection_prompt(
            request=request,
            doctor=request.hospital_doctor,
            thread_id=thread_id,
            version=serializer.validated_data.get("version"),
        )
        return success_response(payload, msg="created", status_code=201)


class DoctorSupplementaryReportView(APIView):
    permission_classes = [DoctorConversationPermission]

    def post(self, request, thread_id):
        serializer = SupplementaryReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = send_supplementary_report_prompt(
            request=request,
            doctor=request.hospital_doctor,
            thread_id=thread_id,
            version=serializer.validated_data.get("version"),
        )
        return success_response(payload, msg="created", status_code=201)


class DoctorConversationMessagesView(APIView):
    permission_classes = [DoctorConversationPermission]

    def get(self, request, thread_id):
        """DOCTOR-WORKSPACE-000004 第 34 问：首屏最近一页，向上按游标加载更早消息。

        Query 参数：
        - before：消息主键游标，只返回 id < before 的更早消息；
        - limit：每页条数（默认 30，最大 100）。
        返回 items 按 (created_at, id) 升序；has_more/next_cursor 供继续向上加载。
        """
        binding = get_doctor_conversation(doctor=request.hospital_doctor, thread_id=thread_id)
        try:
            limit = int(request.query_params.get("limit") or 30)
        except (TypeError, ValueError):
            limit = 30
        limit = max(1, min(100, limit))
        before_raw = request.query_params.get("before")
        qs = (
            ChatMessage.objects.filter(thread=binding.thread, tombstone=False)
            .prefetch_related("blocks")
            .select_related(
                "hospital_attribution__doctor__avatar_file",
                "hospital_attribution__agent__avatar_file",
                "hospital_attribution__agent__doctor__avatar_file",
            )
        )
        if before_raw not in (None, ""):
            try:
                before_id = int(before_raw)
            except (TypeError, ValueError):
                raise HospitalCareError("PAYLOAD_INVALID", details={"field": "before"})
            qs = qs.filter(id__lt=before_id)
        page = list(qs.order_by("-created_at", "-id")[: limit + 1])
        has_more = len(page) > limit
        page = page[:limit]
        page.reverse()
        return success_response(
            {
                "items": [serialize_message(item, binding) for item in page],
                "has_more": has_more,
                "next_cursor": str(page[0].id) if has_more and page else None,
                "version": binding.version,
            }
        )

    def post(self, request, thread_id):
        serializer = DoctorMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doctor = request.hospital_doctor

        def writer():
            payload = send_doctor_message(
                request=request,
                doctor=doctor,
                thread_id=thread_id,
                text=serializer.validated_data["text"],
                version=serializer.validated_data.get("version"),
                attachments=serializer.validated_data.get("attachments"),
            )
            return payload, payload["message_id"]

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={
                "thread_id": str(thread_id),
                "text": serializer.validated_data["text"],
                "attachments": serializer.validated_data.get("attachments") or [],
            },
            resource_type="hospital_message",
            writer=writer,
        )
        return success_response(snapshot)


class DoctorConversationJoinView(APIView):
    permission_classes = [DoctorConversationPermission]

    def post(self, request, thread_id):
        serializer = ConversationVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doctor = request.hospital_doctor

        def writer():
            binding = join_conversation(
                request=request,
                doctor=doctor,
                thread_id=thread_id,
                version=serializer.validated_data["version"],
            )
            return conversation_public(binding, for_doctor=True), binding.thread_id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"thread_id": str(thread_id), "version": serializer.validated_data["version"], "action": "join"},
            resource_type="hospital_conversation",
            writer=writer,
        )
        return success_response(snapshot)


class DoctorConversationLeaveView(APIView):
    """DOCTOR-WORKSPACE-000001 D-015/D-016：医生取消接管，恢复 AI 自动回复。"""

    permission_classes = [DoctorConversationPermission]

    def post(self, request, thread_id):
        serializer = ConversationVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doctor = request.hospital_doctor

        def writer():
            binding = leave_conversation(
                request=request,
                doctor=doctor,
                thread_id=thread_id,
                version=serializer.validated_data["version"],
            )
            return conversation_public(binding, for_doctor=True), binding.thread_id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"thread_id": str(thread_id), "version": serializer.validated_data["version"], "action": "leave"},
            resource_type="hospital_conversation",
            writer=writer,
        )
        return success_response(snapshot)


class DoctorConversationEndView(APIView):
    permission_classes = [DoctorConversationPermission]

    def post(self, request, thread_id):
        serializer = ConversationEndSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doctor = request.hospital_doctor

        def writer():
            binding = end_conversation(
                request=request,
                doctor=doctor,
                thread_id=thread_id,
                payload=serializer.validated_data,
            )
            return conversation_public(binding, for_doctor=True), binding.thread_id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"thread_id": str(thread_id), **serializer.validated_data},
            resource_type="hospital_conversation",
            writer=writer,
        )
        return success_response(snapshot)


class DoctorConversationReadCursorView(APIView):
    """DOCTOR-WORKSPACE-000004 第 20/31 问：消息成功加载后推进已读游标。"""

    permission_classes = [DoctorConversationPermission]

    def post(self, request, thread_id):
        serializer = ReadCursorUpdateSerializer(data=request.data if isinstance(request.data, dict) else {})
        serializer.is_valid(raise_exception=True)
        result = mark_conversation_read(
            request=request,
            doctor=request.hospital_doctor,
            thread_id=thread_id,
            last_read_message_id=serializer.validated_data.get("last_read_message_id"),
        )
        return success_response(result)


class DoctorConversationAttachmentUploadView(APIView):
    """DOCTOR-WORKSPACE-000004 第 16 问：医生上传当前问诊附件（PDF/JPG/PNG）。

    GET 返回当前问诊病历与附件清单（只读）；POST 上传新附件。
    """

    permission_classes = [DoctorConversationPermission]

    def get(self, request, thread_id):
        binding = get_doctor_conversation(doctor=request.hospital_doctor, thread_id=thread_id)
        return success_response({"items": list_conversation_attachments(binding)})

    def post(self, request, thread_id):
        result = upload_conversation_attachment(
            request=request,
            doctor=request.hospital_doctor,
            thread_id=thread_id,
            uploaded=request.FILES.get("file"),
        )
        return success_response({**result, "limits": attachment_limits()}, msg="created", status_code=201)


class StaffWorkLogView(APIView):
    permission_classes = [DoctorConversationPermission]

    def get(self, request):
        actions = [
            "hospital.conversation.join",
            "hospital.conversation.leave",
            "hospital.conversation.attention_update",
            "hospital.conversation.end",
            "hospital.conversation.risk_update",
            "hospital.doctor_message.send",
        ]
        qs = AdminAuditLog.objects.filter(user=request.user, action__in=actions).order_by("-created_at")
        page_obj, pagination = paginate_queryset(qs, request)
        items = [
            {
                "id": item.id,
                "action": item.action,
                "resource_type": item.resource_type,
                "resource_id": item.resource_id,
                "created_at": item.created_at.isoformat(),
                "request_id": item.request_id,
            }
            for item in page_obj.object_list
        ]
        return success_response({"items": items, "pagination": pagination})


class DoctorPatientListView(APIView):
    """DOCTOR-WORKSPACE-000001 D-007~D-010：患者列表（授权集合内搜索/筛选/排序）。"""

    permission_classes = [DoctorConversationPermission]

    def get(self, request):
        doctor = request.hospital_doctor
        items, counts = build_patient_list(
            doctor=doctor,
            keyword=(request.query_params.get("keyword") or "").strip(),
            queue=(request.query_params.get("queue") or "all").strip(),
        )
        page_obj, pagination = paginate_queryset(items, request, default_page_size=50)
        return success_response({"items": list(page_obj.object_list), "pagination": pagination, "counts": counts})


class DoctorConsultPatientListView(APIView):
    """线上问诊工作台患者列表（DOCTOR-WORKSPACE-000004 页面形态修订）。

    与患者工作台患者列表结构一致，但数据源仅为患者客户端提交的线上问诊单；
    未提交问诊的授权患者不进入该列表。
    """

    permission_classes = [DoctorConversationPermission]

    def get(self, request):
        doctor = request.hospital_doctor
        items, counts = build_consult_patient_list(
            doctor=doctor,
            keyword=(request.query_params.get("keyword") or "").strip(),
            queue=(request.query_params.get("queue") or "all").strip(),
        )
        page_obj, pagination = paginate_queryset(items, request, default_page_size=50)
        return success_response({"items": list(page_obj.object_list), "pagination": pagination, "counts": counts})


class DoctorConsultRecordsView(APIView):
    """线上问诊工作台：某患者名下的全部线上问诊记录（含问诊编号与主诉）。"""

    permission_classes = [DoctorConversationPermission]

    def get(self, request, member_id):
        doctor = request.hospital_doctor
        consultations = doctor_member_consultations(doctor=doctor, member_id=member_id)
        thread_ids = [item.binding.thread_id for item in consultations]
        unread_map = unread_counts_by_thread(doctor=doctor, thread_ids=thread_ids)
        attachment_map = attachment_count_for_threads(thread_ids)
        activity_map = conversation_activity_summaries(thread_ids)
        items = []
        for consultation in consultations:
            binding = consultation.binding
            payload = conversation_public(
                binding,
                for_doctor=True,
                unread_count=unread_map.get(binding.thread_id, 0),
                attachment_count=attachment_map.get(binding.thread_id, 0),
            )
            activity = activity_map.get(binding.thread_id) or {}
            payload["first_patient_message_excerpt"] = activity.get("excerpt", "")
            payload["doctor_replied"] = bool(activity.get("doctor_replied"))
            payload["consult_no"] = consultation.consult_no
            payload["chief_complaint"] = consultation.chief_complaint
            payload["submitted_at"] = consultation.submitted_at.isoformat() if consultation.submitted_at else None
            items.append(payload)
        return success_response({"items": items})


class DoctorPatientWorkspaceView(APIView):
    """D-004/D-006：患者工作台只读聚合快照（身份/基础资料/健康档案/医疗安全信息）。

    DOCTOR-WORKSPACE-000004 第 38 问：患者资料读取纳入审计（最小元数据，不记录资料值）。
    """

    permission_classes = [DoctorConversationPermission]

    def get(self, request, member_id):
        doctor = request.hospital_doctor
        payload = build_patient_workspace(doctor=doctor, member_id=member_id)
        write_hospital_audit_log(
            request,
            action="hospital.patient_workspace.read",
            resource_type="hospital_patient",
            resource_id=str(int(member_id)),
            extra={
                "hospital_id": str(doctor.staff_membership.hospital_id),
                "doctor_id": str(doctor.id),
                "member_id": int(member_id),
            },
        )
        return success_response(payload)


class DoctorPatientConversationsView(APIView):
    """D-012/D-013：患者—智能体会话列表；D-019：新建咨询继承当前患者与当前医生智能体。

    线上问诊由独立的 ``/doctor/consult`` 模块展示。两者虽然复用医院会话底层
    模型，但本接口不得返回已关联 ``Consultation`` 问诊单的 Thread。
    """

    permission_classes = [DoctorConversationPermission]

    def get(self, request, member_id):
        doctor = request.hospital_doctor
        bindings = list(doctor_patient_agent_conversations(doctor=doctor, member_id=member_id))
        thread_ids = [item.thread_id for item in bindings]
        unread_map = unread_counts_by_thread(doctor=doctor, thread_ids=thread_ids)
        attachment_map = attachment_count_for_threads(thread_ids)
        activity_map = conversation_activity_summaries(thread_ids)
        items = []
        for item in bindings:
            payload = conversation_public(
                item,
                for_doctor=True,
                unread_count=unread_map.get(item.thread_id, 0),
                attachment_count=attachment_map.get(item.thread_id, 0),
            )
            activity = activity_map.get(item.thread_id) or {}
            payload["first_patient_message_excerpt"] = activity.get("excerpt", "")
            payload["doctor_replied"] = bool(activity.get("doctor_replied"))
            items.append(payload)
        return success_response({"items": items})

    def post(self, request, member_id):
        doctor = request.hospital_doctor

        def writer():
            binding = create_doctor_patient_conversation(request=request, doctor=doctor, member_id=member_id)
            return conversation_public(binding, for_doctor=True), binding.thread_id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"member_id": int(member_id), "action": "create_patient_conversation"},
            resource_type="hospital_conversation",
            writer=writer,
        )
        return success_response(snapshot, msg="created", status_code=201)
