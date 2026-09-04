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
from hospital_care.api.presenters import agent_public, conversation_public, serialize_message, staff_me
from hospital_care.api.staff.serializers import (
    AttentionUpdateSerializer,
    ConversationEndSerializer,
    ConversationVersionSerializer,
    DoctorAgentSubmitSerializer,
    DoctorAgentUpdateSerializer,
    DoctorMessageSerializer,
    PatientSummaryAckSerializer,
)
from hospital_care.permissions import DoctorConversationPermission, HospitalStaffPermission
from hospital_care.realtime import DOCTOR_CONVERSATION_WS_PATH
from hospital_care.selectors.doctor_workspace import doctor_agent, doctor_conversations, doctor_queue_counts, get_doctor_conversation
from hospital_care.selectors.patient_workspace import doctor_patient_conversations
from hospital_care.services.agent_service import submit_agent_for_review, upsert_doctor_agent
from hospital_care.services.conversation_service import end_conversation, join_conversation, leave_conversation, update_attention
from hospital_care.services.doctor_message_service import send_doctor_message
from hospital_care.services.idempotency import run_idempotent_command
from hospital_care.services.patient_workspace_service import (
    ack_summary,
    build_patient_list,
    build_patient_workspace,
    build_risk_card,
    create_doctor_patient_conversation,
    generate_patient_summary,
    get_latest_summary,
    present_summary,
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
        return success_response(
            {
                "items": [conversation_public(item, for_doctor=True) for item in page_obj.object_list],
                "pagination": pagination,
                "counts": doctor_queue_counts(doctor=doctor),
            }
        )


class DoctorConversationDetailView(APIView):
    permission_classes = [DoctorConversationPermission]

    def get(self, request, thread_id):
        binding = get_doctor_conversation(doctor=request.hospital_doctor, thread_id=thread_id)
        return success_response(conversation_public(binding, for_doctor=True))


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


class DoctorConversationMessagesView(APIView):
    permission_classes = [DoctorConversationPermission]

    def get(self, request, thread_id):
        binding = get_doctor_conversation(doctor=request.hospital_doctor, thread_id=thread_id)
        messages = (
            ChatMessage.objects.filter(thread=binding.thread, tombstone=False)
            .prefetch_related("blocks")
            .select_related(
                "hospital_attribution__doctor__avatar_file",
                "hospital_attribution__agent__avatar_file",
                "hospital_attribution__agent__doctor__avatar_file",
            )
            .order_by("created_at", "id")
        )
        return success_response({"items": [serialize_message(item, binding) for item in messages]})

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
            )
            return payload, payload["message_id"]

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"thread_id": str(thread_id), "text": serializer.validated_data["text"]},
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


class DoctorConversationAttentionView(APIView):
    permission_classes = [DoctorConversationPermission]

    def patch(self, request, thread_id):
        serializer = AttentionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doctor = request.hospital_doctor

        def writer():
            binding = update_attention(
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


class StaffWorkLogView(APIView):
    permission_classes = [DoctorConversationPermission]

    def get(self, request):
        actions = [
            "hospital.conversation.join",
            "hospital.conversation.leave",
            "hospital.conversation.attention_update",
            "hospital.conversation.end",
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


class DoctorPatientWorkspaceView(APIView):
    """D-004/D-006：患者工作台只读聚合快照（身份/基础资料/健康档案/医疗安全信息）。"""

    permission_classes = [DoctorConversationPermission]

    def get(self, request, member_id):
        return success_response(build_patient_workspace(doctor=request.hospital_doctor, member_id=member_id))


class DoctorPatientConversationsView(APIView):
    """D-012/D-013：患者会话列表；D-019：新建咨询继承当前患者与当前医生智能体。"""

    permission_classes = [DoctorConversationPermission]

    def get(self, request, member_id):
        bindings = doctor_patient_conversations(doctor=request.hospital_doctor, member_id=member_id)
        return success_response({"items": [conversation_public(item, for_doctor=True) for item in bindings]})

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


class DoctorPatientSummaryView(APIView):
    """D-020/D-023：最新 AI 总结只读查询；进入页面不自动生成。"""

    permission_classes = [DoctorConversationPermission]

    def get(self, request, member_id):
        doctor = request.hospital_doctor
        summary = get_latest_summary(doctor=doctor, member_id=member_id)
        return success_response(present_summary(summary, doctor=doctor))


class DoctorPatientSummaryGenerateView(APIView):
    """D-020：医生主动生成/刷新 AI 总结；生成新版本并保留输入快照。"""

    permission_classes = [DoctorConversationPermission]

    def post(self, request, member_id):
        doctor = request.hospital_doctor

        def writer():
            summary = generate_patient_summary(request=request, doctor=doctor, member_id=member_id)
            return present_summary(summary, doctor=doctor), summary.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"member_id": int(member_id), "action": "generate_patient_summary"},
            resource_type="hospital_patient_summary",
            writer=writer,
        )
        return success_response(snapshot, msg="created", status_code=201)


class DoctorPatientSummaryAckView(APIView):
    """D-023：医生标记/取消“已了解”；不改变总结正文。"""

    permission_classes = [DoctorConversationPermission]

    def post(self, request, member_id):
        serializer = PatientSummaryAckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = ack_summary(
            request=request,
            doctor=request.hospital_doctor,
            member_id=member_id,
            acknowledged=serializer.validated_data["acknowledged"],
        )
        return success_response(payload)


class DoctorPatientRiskView(APIView):
    """D-024~D-026：风险卡片只读查看，复用现有风险信号；不提供人工调整入口。"""

    permission_classes = [DoctorConversationPermission]

    def get(self, request, member_id):
        return success_response(build_risk_card(doctor=request.hospital_doctor, member_id=member_id))
