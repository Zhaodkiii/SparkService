from rest_framework.views import APIView

from common.response import success_response
from hospital_care.api.backoffice.serializers import (
    AgentAvatarUpdateSerializer,
    AgentCreateSerializer,
    AgentReviewSerializer,
    AgentUpdateSerializer,
    DepartmentCreateSerializer,
    DepartmentUpdateSerializer,
    DoctorUpdateSerializer,
    HospitalCreateSerializer,
    HospitalUpdateSerializer,
    HospitalVersionSerializer,
    KnowledgeBaseCreateSerializer,
    KnowledgeBaseUpdateSerializer,
    KnowledgeDocumentCreateSerializer,
    KnowledgeDocumentDeleteSerializer,
    KnowledgeDocumentUpdateSerializer,
    KnowledgeVectorBuildSerializer,
    KnowledgeVersionSerializer,
    StaffCreateSerializer,
    StaffUpdateSerializer,
)
from hospital_care.api.pagination import paginate_queryset
from hospital_care.api.presenters import (
    agent_public,
    catalog_model_option,
    department_public,
    doctor_public,
    embedding_binding_option,
    hospital_admin,
    knowledge_base_public,
    knowledge_document_public,
    staff_admin,
)
from hospital_care.permissions import BackofficeHospitalPermission
from hospital_care.selectors import backoffice_hospital_catalog as catalog
from hospital_care.selectors import hospital_knowledge_catalog as knowledge_catalog
from hospital_care.services.agent_avatar_service import resolve_agent_avatar, set_agent_avatar
from hospital_care.services.agent_provisioning_service import create_clinical_agent, update_clinical_agent
from hospital_care.services.agent_service import review_agent
from hospital_care.services.hospital_admin_service import (
    activate_hospital,
    create_department,
    create_hospital,
    grant_staff,
    suspend_hospital,
    update_department,
    update_doctor,
    update_hospital,
    update_staff,
)
from hospital_care.services.hospital_knowledge_service import (
    build_vectors,
    create_document,
    create_knowledge_base,
    delete_document,
    soft_delete_knowledge_base,
    update_document,
    update_knowledge_base,
)
from hospital_care.services.idempotency import run_idempotent_command


class HospitalListCreateView(APIView):
    permission_classes = [BackofficeHospitalPermission]

    @property
    def required_permission_code(self):
        if self.request.method == "POST":
            return "api:hospital_care:hospital:create"
        return "api:hospital_care:hospital:list"

    def get(self, request):
        qs = catalog.hospital_queryset(
            q=(request.query_params.get("q") or "").strip(),
            status=(request.query_params.get("status") or "").strip(),
            service_mode=(request.query_params.get("service_mode") or "").strip(),
        )
        page_obj, pagination = paginate_queryset(qs, request)
        return success_response(
            {
                "items": [hospital_admin(item) for item in page_obj.object_list],
                "pagination": pagination,
                "counts": catalog.hospital_status_counts(),
            }
        )

    def post(self, request):
        serializer = HospitalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def writer():
            hospital = create_hospital(request=request, payload=serializer.validated_data)
            return hospital_admin(hospital), hospital.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload=serializer.validated_data,
            resource_type="hospital",
            writer=writer,
        )
        return success_response(snapshot, status_code=201)


class HospitalDetailView(APIView):
    permission_classes = [BackofficeHospitalPermission]

    @property
    def required_permission_code(self):
        if self.request.method == "PATCH":
            return "api:hospital_care:hospital:update"
        return "api:hospital_care:hospital:read"

    def get(self, request, hospital_id):
        hospital = catalog.get_hospital(hospital_id)
        return success_response(hospital_admin(hospital, extra={"overview": catalog.hospital_overview(hospital)}))

    def patch(self, request, hospital_id):
        serializer = HospitalUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hospital = update_hospital(request=request, hospital_id=hospital_id, payload=serializer.validated_data)
        return success_response(hospital_admin(hospital))


class HospitalActivateView(APIView):
    permission_classes = [BackofficeHospitalPermission]
    required_permission_code = "api:hospital_care:hospital:activate"

    def post(self, request, hospital_id):
        serializer = HospitalVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def writer():
            hospital = activate_hospital(
                request=request,
                hospital_id=hospital_id,
                version=serializer.validated_data["version"],
            )
            return hospital_admin(hospital), hospital.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"hospital_id": str(hospital_id), "action": "activate", "version": serializer.validated_data["version"]},
            resource_type="hospital",
            writer=writer,
        )
        return success_response(snapshot)


class HospitalSuspendView(APIView):
    permission_classes = [BackofficeHospitalPermission]
    required_permission_code = "api:hospital_care:hospital:suspend"

    def post(self, request, hospital_id):
        serializer = HospitalVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not (serializer.validated_data.get("reason") or "").strip():
            from hospital_care.exceptions import HospitalCareError

            raise HospitalCareError("PAYLOAD_INVALID", details={"field": "reason"})

        def writer():
            hospital = suspend_hospital(
                request=request,
                hospital_id=hospital_id,
                version=serializer.validated_data["version"],
                reason=serializer.validated_data["reason"],
            )
            return hospital_admin(hospital), hospital.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"hospital_id": str(hospital_id), "action": "suspend", **serializer.validated_data},
            resource_type="hospital",
            writer=writer,
        )
        return success_response(snapshot)


class HospitalDepartmentListCreateView(APIView):
    permission_classes = [BackofficeHospitalPermission]

    @property
    def required_permission_code(self):
        if self.request.method == "POST":
            return "api:hospital_care:department:create"
        return "api:hospital_care:department:list"

    def get(self, request, hospital_id):
        catalog.get_hospital(hospital_id)
        qs = catalog.hospital_departments(
            hospital_id,
            q=(request.query_params.get("q") or "").strip(),
            status=(request.query_params.get("status") or "").strip(),
        )
        return success_response({"items": [department_public(item) for item in qs]})

    def post(self, request, hospital_id):
        serializer = DepartmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        department = create_department(request=request, hospital_id=hospital_id, payload=serializer.validated_data)
        return success_response(department_public(department), status_code=201)


class DepartmentDetailView(APIView):
    permission_classes = [BackofficeHospitalPermission]
    required_permission_code = "api:hospital_care:department:update"

    def patch(self, request, department_id):
        serializer = DepartmentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        department = update_department(request=request, department_id=department_id, payload=serializer.validated_data)
        return success_response(department_public(department))


class HospitalStaffListCreateView(APIView):
    permission_classes = [BackofficeHospitalPermission]

    @property
    def required_permission_code(self):
        if self.request.method == "POST":
            return "api:hospital_care:staff:create"
        return "api:hospital_care:staff:list"

    def get(self, request, hospital_id):
        catalog.get_hospital(hospital_id)
        qs = catalog.hospital_staff(hospital_id, q=(request.query_params.get("q") or "").strip())
        page_obj, pagination = paginate_queryset(qs, request)
        items = [staff_admin(membership) for membership in page_obj.object_list]
        return success_response({"items": items, "pagination": pagination})

    def post(self, request, hospital_id):
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = grant_staff(request=request, hospital_id=hospital_id, payload=serializer.validated_data)
        return success_response(
            {
                "id": str(membership.id),
                "user_id": membership.user_id,
                "role": membership.role,
                "status": membership.status,
                "employee_no": membership.employee_no,
            },
            status_code=201,
        )


class HospitalStaffDetailView(APIView):
    permission_classes = [BackofficeHospitalPermission]
    required_permission_code = "api:hospital_care:staff:update"

    def patch(self, request, staff_id):
        serializer = StaffUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = update_staff(request=request, staff_id=staff_id, payload=serializer.validated_data)
        return success_response(staff_admin(membership))


class HospitalDoctorListView(APIView):
    permission_classes = [BackofficeHospitalPermission]
    required_permission_code = "api:hospital_care:doctor:list"

    def get(self, request, hospital_id):
        catalog.get_hospital(hospital_id)
        qs = catalog.hospital_doctors(hospital_id, q=(request.query_params.get("q") or "").strip())
        page_obj, pagination = paginate_queryset(qs, request)
        return success_response(
            {
                "items": [doctor_public(item) for item in page_obj.object_list],
                "pagination": pagination,
            }
        )


class HospitalDoctorDetailView(APIView):
    permission_classes = [BackofficeHospitalPermission]
    required_permission_code = "api:hospital_care:doctor:update"

    def patch(self, request, doctor_id):
        serializer = DoctorUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doctor = update_doctor(request=request, doctor_id=doctor_id, payload=serializer.validated_data)
        return success_response(doctor_public(doctor))


class HospitalAgentListCreateView(APIView):
    permission_classes = [BackofficeHospitalPermission]

    @property
    def required_permission_code(self):
        if self.request.method == "POST":
            return "api:hospital_care:agent:create"
        return "api:hospital_care:agent:list"

    def get(self, request, hospital_id):
        catalog.get_hospital(hospital_id)
        qs = catalog.hospital_agents(
            hospital_id,
            q=(request.query_params.get("q") or "").strip(),
            status=(request.query_params.get("status") or "").strip(),
            department_id=request.query_params.get("department_id") or None,
        )
        page_obj, pagination = paginate_queryset(qs, request)
        return success_response(
            {
                "items": [agent_public(item, include_internal=True) for item in page_obj.object_list],
                "pagination": pagination,
            }
        )

    def post(self, request, hospital_id):
        serializer = AgentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def writer():
            agent = create_clinical_agent(request=request, hospital_id=hospital_id, payload=serializer.validated_data)
            return agent_public(knowledge_catalog.get_agent(agent.id), include_internal=True), agent.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"hospital_id": str(hospital_id), **serializer.validated_data},
            resource_type="hospital_agent",
            writer=writer,
        )
        return success_response(snapshot, status_code=201)


class HospitalAgentFormOptionsView(APIView):
    permission_classes = [BackofficeHospitalPermission]
    required_permission_code = "api:hospital_care:agent:list"

    def get(self, request, hospital_id):
        catalog.get_hospital(hospital_id)
        options = knowledge_catalog.agent_form_options(hospital_id)
        return success_response(
            {
                "doctors": [doctor_public(item) for item in options["doctors"]],
                "departments": [department_public(item) for item in options["departments"]],
                "models": [catalog_model_option(item) for item in options["models"]],
                "knowledge_bases": [
                    {"id": str(item.id), "name": item.name, "vector_status": item.vector_status}
                    for item in options["knowledge_bases"]
                ],
                "embedding_bindings": [embedding_binding_option(item) for item in options["embedding_bindings"]],
                "ai_tool_scenarios": options["ai_tool_scenarios"],
                "server_tool_scenarios": options["server_tool_scenarios"],
            }
        )


class AgentDetailView(APIView):
    permission_classes = [BackofficeHospitalPermission]

    @property
    def required_permission_code(self):
        if self.request.method == "PATCH":
            return "api:hospital_care:agent:update"
        return "api:hospital_care:agent:read"

    def get(self, request, agent_id):
        agent = knowledge_catalog.get_agent(agent_id)
        return success_response(agent_public(agent, include_internal=True))

    def patch(self, request, agent_id):
        serializer = AgentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def writer():
            agent = update_clinical_agent(request=request, agent_id=agent_id, payload=serializer.validated_data)
            return agent_public(knowledge_catalog.get_agent(agent.id), include_internal=True), agent.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"agent_id": str(agent_id), **serializer.validated_data},
            resource_type="hospital_agent",
            writer=writer,
        )
        return success_response(snapshot)


class AgentAvatarView(APIView):
    """已有智能体头像立即切换（上传专属头像 / 切回复用医生头像）。"""

    permission_classes = [BackofficeHospitalPermission]
    required_permission_code = "api:hospital_care:agent:update"

    def patch(self, request, agent_id):
        serializer = AgentAvatarUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def writer():
            agent = set_agent_avatar(
                agent_id=agent_id,
                avatar_source=serializer.validated_data["avatar_source"],
                avatar_file_id=serializer.validated_data.get("avatar_file_id"),
                version=serializer.validated_data["version"],
            )
            resolved = resolve_agent_avatar(agent)
            return {
                "id": str(agent.id),
                "avatar_source": agent.avatar_source,
                "avatar_file_id": agent.avatar_file_id,
                "avatar_url": resolved.url,
                "avatar_version": resolved.version,
                "version": agent.version,
            }, agent.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"agent_id": str(agent_id), **serializer.validated_data},
            resource_type="clinical_agent_avatar",
            writer=writer,
        )
        return success_response(snapshot)


class AgentReviewView(APIView):
    permission_classes = [BackofficeHospitalPermission]
    required_permission_code = "api:hospital_care:agent:review"

    def post(self, request, agent_id):
        serializer = AgentReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def writer():
            agent = review_agent(request=request, agent_id=agent_id, payload=serializer.validated_data)
            return agent_public(agent, include_internal=True), agent.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"agent_id": str(agent_id), **serializer.validated_data},
            resource_type="clinical_agent",
            writer=writer,
        )
        return success_response(snapshot)


class HospitalAuditLogView(APIView):
    permission_classes = [BackofficeHospitalPermission]
    required_permission_code = "api:hospital_care:audit:list"

    def get(self, request, hospital_id):
        catalog.get_hospital(hospital_id)
        qs = catalog.hospital_audit_logs(hospital_id, action=(request.query_params.get("action") or "").strip())
        page_obj, pagination = paginate_queryset(qs, request)
        items = [
            {
                "id": item.id,
                "action": item.action,
                "user_id": item.user_id,
                "resource_type": item.resource_type,
                "resource_id": item.resource_id,
                "status_code": item.status_code,
                "request_id": item.request_id,
                "created_at": item.created_at.isoformat(),
            }
            for item in page_obj.object_list
        ]
        return success_response({"items": items, "pagination": pagination})


class HospitalKnowledgeBaseListCreateView(APIView):
    permission_classes = [BackofficeHospitalPermission]

    @property
    def required_permission_code(self):
        if self.request.method == "POST":
            return "api:hospital_care:knowledge:create"
        return "api:hospital_care:knowledge:list"

    def get(self, request, hospital_id):
        from hospital_care.services.ai_catalog import embedding_bindings_for_form

        catalog.get_hospital(hospital_id)
        qs = knowledge_catalog.hospital_knowledge_bases(
            hospital_id,
            q=(request.query_params.get("q") or "").strip(),
            department_id=request.query_params.get("department_id") or None,
        )
        page_obj, pagination = paginate_queryset(qs, request)
        items = knowledge_catalog.attach_knowledge_list_stats(list(page_obj.object_list))
        payload = []
        for item in items:
            item.agent_count = knowledge_catalog.knowledge_agent_count(item)
            payload.append(knowledge_base_public(item))
        return success_response(
            {
                "items": payload,
                "pagination": pagination,
                "embedding_bindings": [embedding_binding_option(row) for row in embedding_bindings_for_form()],
            }
        )

    def post(self, request, hospital_id):
        serializer = KnowledgeBaseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def writer():
            profile = create_knowledge_base(request=request, hospital_id=hospital_id, payload=serializer.validated_data)
            return knowledge_base_public(knowledge_catalog.get_knowledge_base(profile.id)), profile.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"hospital_id": str(hospital_id), **serializer.validated_data},
            resource_type="hospital_knowledge",
            writer=writer,
        )
        return success_response(snapshot, status_code=201)


class KnowledgeBaseDetailView(APIView):
    permission_classes = [BackofficeHospitalPermission]

    @property
    def required_permission_code(self):
        if self.request.method == "PATCH":
            return "api:hospital_care:knowledge:update"
        if self.request.method == "DELETE":
            return "api:hospital_care:knowledge:delete"
        return "api:hospital_care:knowledge:read"

    def get(self, request, profile_id):
        from hospital_care.services.ai_catalog import embedding_bindings_for_form

        profile = knowledge_catalog.get_knowledge_base(profile_id)
        documents = [knowledge_document_public(item) for item in knowledge_catalog.knowledge_documents(profile)]
        return success_response(
            knowledge_base_public(
                profile,
                extra={
                    "agent_count": knowledge_catalog.knowledge_agent_count(profile),
                    "documents": documents,
                    "document_count": len(documents),
                    "embedding_bindings": [embedding_binding_option(item) for item in embedding_bindings_for_form()],
                },
            )
        )

    def patch(self, request, profile_id):
        serializer = KnowledgeBaseUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def writer():
            profile = update_knowledge_base(request=request, profile_id=profile_id, payload=serializer.validated_data)
            return knowledge_base_public(knowledge_catalog.get_knowledge_base(profile.id)), profile.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"profile_id": str(profile_id), **serializer.validated_data},
            resource_type="hospital_knowledge",
            writer=writer,
        )
        return success_response(snapshot)

    def delete(self, request, profile_id):
        serializer = KnowledgeVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def writer():
            profile = soft_delete_knowledge_base(
                request=request,
                profile_id=profile_id,
                version=serializer.validated_data["version"],
            )
            return {"id": str(profile.id), "is_deleted": True, "version": profile.version}, profile.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"profile_id": str(profile_id), "action": "delete", **serializer.validated_data},
            resource_type="hospital_knowledge",
            writer=writer,
        )
        return success_response(snapshot)


class KnowledgeDocumentListCreateView(APIView):
    permission_classes = [BackofficeHospitalPermission]

    @property
    def required_permission_code(self):
        if self.request.method == "POST":
            return "api:hospital_care:knowledge:document_create"
        return "api:hospital_care:knowledge:read"

    def get(self, request, profile_id):
        profile = knowledge_catalog.get_knowledge_base(profile_id)
        return success_response({"items": [knowledge_document_public(item) for item in knowledge_catalog.knowledge_documents(profile)]})

    def post(self, request, profile_id):
        serializer = KnowledgeDocumentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def writer():
            document = create_document(request=request, profile_id=profile_id, payload=serializer.validated_data)
            profile = knowledge_catalog.get_knowledge_base(profile_id)
            return {
                "document": knowledge_document_public(document),
                "knowledge_base": knowledge_base_public(profile),
            }, document.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"profile_id": str(profile_id), **serializer.validated_data},
            resource_type="hospital_knowledge_document",
            writer=writer,
        )
        return success_response(snapshot, status_code=201)


class KnowledgeDocumentDetailView(APIView):
    permission_classes = [BackofficeHospitalPermission]

    @property
    def required_permission_code(self):
        if self.request.method == "DELETE":
            return "api:hospital_care:knowledge:document_delete"
        return "api:hospital_care:knowledge:document_update"

    def patch(self, request, profile_id, document_id):
        serializer = KnowledgeDocumentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def writer():
            document = update_document(
                request=request,
                profile_id=profile_id,
                document_id=document_id,
                payload=serializer.validated_data,
            )
            profile = knowledge_catalog.get_knowledge_base(profile_id)
            return {
                "document": knowledge_document_public(document),
                "knowledge_base": knowledge_base_public(profile),
            }, document.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"profile_id": str(profile_id), "document_id": str(document_id), **serializer.validated_data},
            resource_type="hospital_knowledge_document",
            writer=writer,
        )
        return success_response(snapshot)

    def delete(self, request, profile_id, document_id):
        serializer = KnowledgeDocumentDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def writer():
            document = delete_document(
                request=request,
                profile_id=profile_id,
                document_id=document_id,
                revision=serializer.validated_data["revision"],
            )
            profile = knowledge_catalog.get_knowledge_base(profile_id)
            return {
                "document_id": str(document.id),
                "is_deleted": True,
                "knowledge_base": knowledge_base_public(profile),
            }, document.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={
                "profile_id": str(profile_id),
                "document_id": str(document_id),
                "action": "delete",
                **serializer.validated_data,
            },
            resource_type="hospital_knowledge_document",
            writer=writer,
        )
        return success_response(snapshot)


class KnowledgeVectorBuildView(APIView):
    permission_classes = [BackofficeHospitalPermission]
    required_permission_code = "api:hospital_care:knowledge:vector_build"

    def post(self, request, profile_id):
        serializer = KnowledgeVectorBuildSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def writer():
            profile = build_vectors(
                request=request,
                profile_id=profile_id,
                embedding_binding_id=serializer.validated_data["embedding_binding_id"],
                version=serializer.validated_data["version"],
            )
            refreshed = knowledge_catalog.get_knowledge_base(profile.id)
            return knowledge_base_public(refreshed), profile.id

        snapshot, _ = run_idempotent_command(
            request=request,
            payload={"profile_id": str(profile_id), **serializer.validated_data},
            resource_type="hospital_knowledge",
            writer=writer,
        )
        return success_response(snapshot)
