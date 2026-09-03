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
)
from hospital_care.permissions import DoctorConversationPermission, HospitalStaffPermission
from hospital_care.realtime import DOCTOR_CONVERSATION_WS_PATH
from hospital_care.selectors.doctor_workspace import doctor_agent, doctor_conversations, doctor_queue_counts, get_doctor_conversation
from hospital_care.services.agent_service import submit_agent_for_review, upsert_doctor_agent
from hospital_care.services.conversation_service import end_conversation, join_conversation, update_attention
from hospital_care.services.doctor_message_service import send_doctor_message
from hospital_care.services.idempotency import run_idempotent_command


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
            .prefetch_related("blocks", "hospital_attribution")
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
