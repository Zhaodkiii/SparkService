from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from ai_config.provider_resolution import (
    build_provider_index,
    load_active_api_providers,
    resolve_provider_for_model,
)
from common.response import success_response
from hospital_care.api.pagination import paginate_queryset
from hospital_care.api.patient.serializers import AppointmentRedirectSerializer, CreateConversationSerializer
from hospital_care.api.presenters import (
    agent_public,
    agent_runtime_config_public,
    conversation_public,
    department_public,
    hospital_public,
)
from hospital_care.exceptions import HospitalCareError
from hospital_care.models import ClinicalAgentProfile, DoctorProfile, Hospital
from hospital_care.models.organization import HospitalDepartment
from hospital_care.selectors import patient_catalog, patient_knowledge
from hospital_care.services.conversation_service import create_patient_conversation
from hospital_care.services.idempotency import run_idempotent_command
from medical.models import Member
from medical.services.member_binding_service import ensure_can_access_member


def _current_member_summary(request, hospital):
    member_id = request.query_params.get("member_id")
    if not member_id:
        return None
    try:
        ensure_can_access_member(user=request.user, member_id=int(member_id))
    except (PermissionError, ValueError) as exc:
        raise HospitalCareError("MEMBER_ACCESS_DENIED") from exc
    member = Member.all_objects.filter(pk=int(member_id), is_deleted=False).first()
    if member is None:
        raise HospitalCareError("MEMBER_ACCESS_DENIED")
    return {"member_id": member.id, "display_name": member.name, "hospital_id": str(hospital.id)}


class HospitalListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        page_obj, pagination = paginate_queryset(patient_catalog.active_hospitals().order_by("name"), request)
        return success_response(
            {
                "items": [hospital_public(item) for item in page_obj.object_list],
                "pagination": pagination,
            }
        )


class HospitalHomeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, hospital_id):
        hospital = patient_catalog.get_active_hospital(hospital_id)
        departments = [department_public(item) for item in patient_catalog.active_departments(hospital.id)[:12]]
        agents = [agent_public(item) for item in patient_catalog.published_agents(hospital_id=hospital.id)[:8]]
        return success_response(
            {
                "hospital": hospital_public(hospital),
                "current_member": _current_member_summary(request, hospital),
                "quick_services": [
                    {"key": "registration", "title": "预约挂号", "available": hospital.service_mode != Hospital.ServiceMode.INTEGRATED},
                    {"key": "ai_triage", "title": "AI 导诊", "available": True},
                    {"key": "report", "title": "报告解读", "available": True},
                ],
                "departments": departments,
                "recommended_agents": agents,
            }
        )


class HospitalDepartmentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, hospital_id):
        hospital = patient_catalog.get_active_hospital(hospital_id)
        items = [department_public(item) for item in patient_catalog.active_departments(hospital.id)]
        return success_response({"items": items})


class HospitalAgentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, hospital_id):
        patient_catalog.get_active_hospital(hospital_id)
        qs = patient_catalog.published_agents(
            hospital_id=hospital_id,
            department_id=request.query_params.get("department_id") or None,
            keyword=(request.query_params.get("keyword") or "").strip(),
        )
        page_obj, pagination = paginate_queryset(qs, request)
        return success_response(
            {
                "items": [agent_public(item) for item in page_obj.object_list],
                "pagination": pagination,
            }
        )


class AgentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, agent_id):
        agent = patient_catalog.get_published_agent(agent_id)
        return success_response(agent_public(agent))


class AgentRuntimeConfigView(APIView):
    """CHAT-000058：医院医生智能体专用运行配置。

    GET /api/v1/hospital-care/agents/{agent_id}/runtime-config/?member_id={member_id}

    只返回当前 agent_id 对应唯一医生智能体的直连运行配置；失败按稳定业务错误码
    拒绝，不返回其他智能体或通用模型候选。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, agent_id):
        raw_member_id = request.query_params.get("member_id")
        if not raw_member_id:
            raise HospitalCareError("PAYLOAD_INVALID", details={"field": "member_id"})
        try:
            member_id = int(raw_member_id)
            ensure_can_access_member(user=request.user, member_id=member_id)
        except (PermissionError, ValueError) as exc:
            raise HospitalCareError("MEMBER_ACCESS_DENIED") from exc
        member = Member.all_objects.filter(pk=member_id, is_deleted=False).first()
        if member is None:
            raise HospitalCareError("MEMBER_ACCESS_DENIED")

        agent = (
            ClinicalAgentProfile.objects.select_related(
                "hospital",
                "department",
                "doctor",
                "doctor__avatar_file",
                "avatar_file",
                "scenario_binding",
                "scenario_binding__model",
            )
            .filter(pk=agent_id)
            .first()
        )
        if agent is None:
            raise HospitalCareError("AGENT_NOT_FOUND")
        if (
            agent.publication_status != ClinicalAgentProfile.PublicationStatus.PUBLISHED
            or agent.hospital.status != Hospital.Status.ACTIVE
            or agent.department.status != HospitalDepartment.Status.ACTIVE
            or agent.doctor.profile_status != DoctorProfile.ProfileStatus.ACTIVE
        ):
            raise HospitalCareError("AGENT_UNAVAILABLE")

        binding = agent.scenario_binding
        if binding is None or not binding.is_active:
            raise HospitalCareError("AGENT_BINDING_INVALID")
        model = binding.model
        if model is None or not model.is_active:
            raise HospitalCareError("RUNTIME_CONFIG_INVALID")

        provider = resolve_provider_for_model(
            model.company,
            build_provider_index(load_active_api_providers()),
        )
        if provider is None or not provider["endpoint"] or not provider["api_key"]:
            raise HospitalCareError("RUNTIME_CONFIG_INVALID")

        return success_response(agent_runtime_config_public(agent, member_id=member_id, provider=provider))


class ConversationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member_id = request.query_params.get("member_id")
        qs = patient_catalog.patient_conversations(
            user=request.user,
            member_id=int(member_id) if member_id else None,
        )
        page_obj, pagination = paginate_queryset(qs, request)
        return success_response(
            {
                "items": [conversation_public(item) for item in page_obj.object_list],
                "pagination": pagination,
            }
        )

    def post(self, request):
        serializer = CreateConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        def writer():
            binding = create_patient_conversation(
                request=request,
                user=request.user,
                agent_id=data["agent_id"],
                member_id=data["member_id"],
                thread_id=data.get("thread_id"),
            )
            snapshot = {
                "thread_id": str(binding.thread_id),
                "conversation": conversation_public(binding),
            }
            return snapshot, binding.thread_id

        payload, _replayed = run_idempotent_command(
            request=request,
            payload={"agent_id": str(data["agent_id"]), "member_id": data["member_id"], "thread_id": str(data.get("thread_id") or "")},
            resource_type="hospital_conversation",
            writer=writer,
        )
        return success_response(payload)


class PatientConversationContextView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, thread_id):
        member_id = request.query_params.get("member_id")
        binding = patient_catalog.get_patient_conversation(
            user=request.user,
            thread_id=thread_id,
            member_id=int(member_id) if member_id else None,
        )
        payload = conversation_public(binding)
        # CHAT-000055 Q22/Q27：context 是会话能力与知识 Manifest 的单一事实源。
        payload["capabilities"] = patient_knowledge.conversation_capabilities(binding)
        payload["knowledge_manifest"] = patient_knowledge.agent_knowledge_manifest(binding.agent)
        return success_response(payload)


class PatientKnowledgeSyncPullView(APIView):
    """CHAT-000055 Q23：按 knowledge_base_id 的患者端只读增量 pull。

    Demo 授权口径（Q24）：登录即可读取未删除医院科普库，不做 agent 绑定授权；
    与按 request.user 隔离的个人知识 pull 路由完全分离。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, knowledge_base_id):
        cursor = request.query_params.get("cursor") or None
        limit = request.query_params.get("limit")
        payload = patient_knowledge.pull_knowledge_base_delta(
            knowledge_base_id=knowledge_base_id,
            cursor=cursor,
            limit=int(limit) if limit else None,
        )
        return success_response(payload)


class RegistrationEntryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, hospital_id):
        hospital = patient_catalog.get_active_hospital(hospital_id)
        if hospital.service_mode == Hospital.ServiceMode.INTEGRATED:
            raise HospitalCareError("REGISTRATION_INTEGRATION_UNAVAILABLE")
        return success_response(
            {
                "hospital_id": str(hospital.id),
                "service_mode": hospital.service_mode,
                "demo": hospital.service_mode == Hospital.ServiceMode.DEMO,
                "redirect_url": hospital.registration_redirect_url if hospital.service_mode == Hospital.ServiceMode.REDIRECT else "",
                "notice": "仅用于产品演示，不产生真实挂号" if hospital.service_mode == Hospital.ServiceMode.DEMO else "将跳转医院官方入口，Spark 不记录挂号结果",
            }
        )


class AppointmentRedirectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AppointmentRedirectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ensure_can_access_member(user=request.user, member_id=serializer.validated_data["member_id"])
        except PermissionError as exc:
            raise HospitalCareError("MEMBER_ACCESS_DENIED") from exc
        hospital = patient_catalog.get_active_hospital(serializer.validated_data["hospital_id"])
        if hospital.service_mode == Hospital.ServiceMode.INTEGRATED:
            raise HospitalCareError("REGISTRATION_INTEGRATION_UNAVAILABLE")
        return success_response(
            {
                "hospital_id": str(hospital.id),
                "service_mode": hospital.service_mode,
                "redirect_url": hospital.registration_redirect_url if hospital.service_mode == Hospital.ServiceMode.REDIRECT else "",
                "demo": hospital.service_mode == Hospital.ServiceMode.DEMO,
            }
        )
