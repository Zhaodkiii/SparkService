from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.serializers import Serializer, CharField
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from accounts.models import AccountDeactivation
from ai_config.models import AIModelCatalog, AIProviderKeyConfig, AIScenarioModelBinding, ScenarioKey, TrialApplication
from ai_config.services import TrialService
from chat_sync.models import ChatMessage, ChatThread
from common.permissions import AdminCodePermission, AdminOnlyPermission
from common.response import error_response, success_response
from django_celery_beat.models import PeriodicTask
from django_celery_results.models import TaskResult
from file_manager.models import ManagedFile
from medical.models import MedicalCase, Member

from backoffice.audit import write_audit_log
from backoffice.models import AdminAuditLog, AdminPermission, AdminRole, AdminRolePermission, AdminUserRole
from backoffice.rbac import bootstrap_admin_permissions, get_user_menu_tree, get_user_permission_codes, get_user_role_codes
from backoffice.serializers import (
    AdminAIModelCatalogCreateSerializer,
    AdminAIModelCatalogSerializer,
    AdminAIModelCatalogUpdateSerializer,
    AdminAIProviderKeyCreateSerializer,
    AdminAIProviderKeySerializer,
    AdminAIProviderKeyUpdateSerializer,
    AdminAIScenarioModelBindingSerializer,
    AdminAuditLogSerializer,
    AdminPermissionSerializer,
    AdminRolePermissionAssignSerializer,
    AdminRoleSerializer,
    AdminTrialActionSerializer,
    AdminTrialApplicationSerializer,
    AdminUserRoleAssignSerializer,
    AdminUserSerializer,
    AdminUserStatusSerializer,
)


User = get_user_model()


class AdminLoginSerializer(Serializer):
    username = CharField(max_length=150)
    password = CharField(max_length=128)


class AdminAuthLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        user = authenticate(request=request, username=username, password=password)
        if user is None or not user.is_active:
            write_audit_log(request, action="admin.login.failed", resource_type="auth", status_code=401)
            return error_response(msg="invalid_credentials", code=40101, status_code=status.HTTP_401_UNAUTHORIZED)

        if not (user.is_staff or user.is_superuser):
            write_audit_log(request, action="admin.login.denied", resource_type="auth", status_code=403)
            return error_response(msg="not_admin_user", code=40301, status_code=status.HTTP_403_FORBIDDEN)

        token = TokenObtainPairSerializer.get_token(user)
        payload = {
            "access": str(token.access_token),
            "refresh": str(token),
            "user": AdminUserSerializer(user).data,
        }
        write_audit_log(request, action="admin.login.success", resource_type="auth", resource_id=str(user.id), status_code=200)
        return success_response(payload, msg="login_success", code=0, status_code=status.HTTP_200_OK)


class AdminAuthProfileView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        bootstrap_admin_permissions()
        role_codes = get_user_role_codes(request.user.id)
        permission_codes = get_user_permission_codes(request.user.id)
        payload = {
            "user": AdminUserSerializer(request.user).data,
            "roles": role_codes,
            "permissions": permission_codes,
            "menus": get_user_menu_tree(request.user.id),
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminDashboardOverviewView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        payload = {
            "users": {
                "total": User.objects.count(),
                "active": User.objects.filter(is_active=True).count(),
                "staff": User.objects.filter(is_staff=True).count(),
            },
            "chat": {
                "threads": ChatThread.objects.filter(is_deleted=False).count(),
                "messages": ChatMessage.objects.filter(tombstone=False).count(),
            },
            "medical": {
                "members": Member.objects.filter(is_deleted=False).count(),
                "cases": MedicalCase.objects.filter(is_deleted=False).count(),
            },
            "files": {
                "managed": ManagedFile.objects.filter(is_deleted=False).count(),
                "public": ManagedFile.objects.filter(is_deleted=False, is_public=True).count(),
            },
            "deactivation": {
                "requested": AccountDeactivation.objects.filter(state=AccountDeactivation.DeactivationState.REQUESTED).count(),
                "failed": AccountDeactivation.objects.filter(state=AccountDeactivation.DeactivationState.FAILED).count(),
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminUserListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = User.objects.all().order_by("-date_joined", "-id")
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(Q(username__icontains=query) | Q(email__icontains=query))

        is_active = request.query_params.get("is_active")
        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))

        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)

        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        rows = AdminUserSerializer(page_obj.object_list, many=True).data
        payload = {
            "items": rows,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminUserStatusView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:user:status:update"

    def post(self, request, user_id: int):
        target = get_object_or_404(User, pk=user_id)
        serializer = AdminUserStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if target.id == request.user.id and serializer.validated_data["is_active"] is False:
            return success_response(
                {"detail": "cannot_deactivate_self"},
                msg="invalid_operation",
                code=40001,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        target.is_active = serializer.validated_data["is_active"]
        target.save(update_fields=["is_active"])

        payload = AdminUserSerializer(target).data
        write_audit_log(
            request,
            action="admin.user.status.update",
            resource_type="user",
            resource_id=str(target.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


SCENARIO_LABEL_ZH = {
    "chat": "对话",
    "optimization_text": "文本优化模型",
    "optimization_visual": "视觉优化模型",
    "context_folding": "上下文折叠",
    "router": "Router 模型",
    "model_config": "模型配置",
    "report_interpretation": "报告解读模型",
}


def _scenario_key_valid(scenario_key: str) -> bool:
    return scenario_key in {m.value for m in ScenarioKey}


class AdminAIScenarioSummaryListView(APIView):
    """Fixed seven scenarios: aggregate counts and default model per scenario."""

    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        rows_out = []
        for member in ScenarioKey:
            key = member.value
            qs = AIScenarioModelBinding.objects.filter(scenario=key)
            active = qs.filter(is_active=True).order_by("position", "id")
            default_row = active.filter(is_default=True).first()
            rows_out.append(
                {
                    "scenario": key,
                    "label": SCENARIO_LABEL_ZH.get(key, key),
                    "models_count": qs.count(),
                    "default_model": default_row.model.name if default_row else None,
                    "active_bindings": active.count(),
                }
            )
        return success_response(rows_out, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminAIScenarioBindingListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, scenario_key: str):
        if not _scenario_key_valid(scenario_key):
            return error_response(msg="invalid_scenario", code=40001, status_code=status.HTTP_400_BAD_REQUEST)
        rows = (
            AIScenarioModelBinding.objects.select_related("model")
            .filter(scenario=scenario_key)
            .order_by("position", "id")
        )
        payload = AdminAIScenarioModelBindingSerializer(rows, many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request, scenario_key: str):
        permission_codes = get_user_permission_codes(request.user.id)
        if not request.user.is_superuser and "button:ai:scenario:create" not in permission_codes:
            return error_response(msg="permission_denied", code=40301, status_code=status.HTTP_403_FORBIDDEN)
        if not _scenario_key_valid(scenario_key):
            return error_response(msg="invalid_scenario", code=40001, status_code=status.HTTP_400_BAD_REQUEST)
        serializer = AdminAIScenarioModelBindingSerializer(data=request.data, context={"scenario": scenario_key})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
        payload = serializer.data
        write_audit_log(
            request,
            action="admin.ai.scenario_binding.create",
            resource_type="ai_scenario_binding",
            resource_id=str(payload["id"]),
            status_code=201,
            response_payload=payload,
        )
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminAIScenarioBindingDetailView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:scenario:update"

    def patch(self, request, binding_id: int):
        row = get_object_or_404(AIScenarioModelBinding, pk=binding_id)
        serializer = AdminAIScenarioModelBindingSerializer(row, data=request.data, partial=True, context={"scenario": row.scenario})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
        payload = serializer.data
        write_audit_log(
            request,
            action="admin.ai.scenario_binding.update",
            resource_type="ai_scenario_binding",
            resource_id=str(row.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)

    def delete(self, request, binding_id: int):
        row = get_object_or_404(AIScenarioModelBinding, pk=binding_id)
        others = AIScenarioModelBinding.objects.filter(scenario=row.scenario).exclude(pk=row.pk)
        if not others.exists():
            return error_response(msg="cannot_delete_last_binding", code=40001, status_code=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            was_default = row.is_default
            row.delete()
            if was_default:
                nxt = others.filter(is_active=True).order_by("position", "id").first() or others.order_by("position", "id").first()
                if nxt and not AIScenarioModelBinding.objects.filter(scenario=nxt.scenario, is_default=True).exists():
                    nxt.is_default = True
                    nxt.save()
        write_audit_log(
            request,
            action="admin.ai.scenario_binding.delete",
            resource_type="ai_scenario_binding",
            resource_id=str(binding_id),
            status_code=200,
            response_payload={},
        )
        return success_response({}, msg="deleted", code=0, status_code=status.HTTP_200_OK)


class AdminAIModelCatalogListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        rows = AIModelCatalog.objects.all().order_by("position", "name")
        payload = AdminAIModelCatalogSerializer(rows, many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request):
        permission_codes = get_user_permission_codes(request.user.id)
        if not request.user.is_superuser and "button:ai:model:create" not in permission_codes:
            return error_response(msg="permission_denied", code=40301, status_code=status.HTTP_403_FORBIDDEN)
        serializer = AdminAIModelCatalogCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = serializer.save()
        payload = AdminAIModelCatalogSerializer(row).data
        write_audit_log(
            request,
            action="admin.ai.model_catalog.create",
            resource_type="ai_model_catalog",
            resource_id=str(row.id),
            status_code=201,
            response_payload=payload,
        )
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminAIModelCatalogDetailView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:model:update"

    def patch(self, request, catalog_id: int):
        row = get_object_or_404(AIModelCatalog, pk=catalog_id)
        serializer = AdminAIModelCatalogUpdateSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        payload = AdminAIModelCatalogSerializer(row).data
        write_audit_log(
            request,
            action="admin.ai.model_catalog.update",
            resource_type="ai_model_catalog",
            resource_id=str(row.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminAIProviderKeyListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        kind = (request.query_params.get("kind") or "").strip()
        queryset = AIProviderKeyConfig.objects.all().order_by("kind", "position", "company", "name")
        if kind:
            queryset = queryset.filter(kind=kind)
        payload = AdminAIProviderKeySerializer(queryset, many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request):
        permission_codes = get_user_permission_codes(request.user.id)
        if not request.user.is_superuser and "button:ai:provider:create" not in permission_codes:
            return error_response(msg="permission_denied", code=40301, status_code=status.HTTP_403_FORBIDDEN)
        serializer = AdminAIProviderKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = serializer.save()
        payload = AdminAIProviderKeySerializer(row).data
        write_audit_log(
            request,
            action="admin.ai.provider.create",
            resource_type="ai_provider",
            resource_id=str(row.id),
            status_code=201,
            response_payload=payload,
        )
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminAIProviderKeyDetailView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:provider:update"

    def patch(self, request, provider_id: int):
        row = get_object_or_404(AIProviderKeyConfig, pk=provider_id)
        serializer = AdminAIProviderKeyUpdateSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        payload = AdminAIProviderKeySerializer(row).data
        write_audit_log(
            request,
            action="admin.ai.provider.update",
            resource_type="ai_provider",
            resource_id=str(row.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminAITrialListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = TrialApplication.objects.select_related("user").all().order_by("-created_at", "-id")
        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        payload = {
            "items": AdminTrialApplicationSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminAITrialActionView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:trial:approve"

    @transaction.atomic
    def post(self, request, trial_id: int, action: str):
        trial = get_object_or_404(TrialApplication.objects.select_for_update(), pk=trial_id)
        serializer = AdminTrialActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data.get("note", "").strip()

        now = timezone.now()
        if action == "approve":
            trial.status = TrialApplication.Status.ACTIVE
            trial.grant_source = TrialApplication.GrantSource.MANUAL
            trial.started_at = now
            trial.expires_at = now + timedelta(days=TrialService._trial_days())
            trial.approved_at = now
            trial.rejected_at = None
            required_code = "button:ai:trial:approve"
        elif action == "reject":
            trial.status = TrialApplication.Status.REJECTED
            trial.grant_source = TrialApplication.GrantSource.MANUAL
            trial.rejected_at = now
            trial.approved_at = None
            required_code = "button:ai:trial:reject"
        elif action == "recycle":
            trial.status = TrialApplication.Status.EXPIRED
            trial.expires_at = now
            required_code = "button:ai:trial:recycle"
        else:
            return error_response(msg="invalid_action", code=40001, status_code=status.HTTP_400_BAD_REQUEST)

        if not request.user.is_superuser and required_code not in get_user_permission_codes(request.user.id):
            return error_response(msg="permission_denied", code=40301, status_code=status.HTTP_403_FORBIDDEN)

        if note:
            trial.note = note
        trial.save()

        payload = AdminTrialApplicationSerializer(trial).data
        write_audit_log(
            request,
            action=f"admin.ai.trial.{action}",
            resource_type="trial_application",
            resource_id=str(trial.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminAsyncTaskDashboardView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        since_24h = timezone.now() - timedelta(hours=24)
        recent = TaskResult.objects.filter(date_done__gte=since_24h)
        status_counter = {}
        for key in ["SUCCESS", "FAILURE", "PENDING", "STARTED", "RETRY", "REVOKED"]:
            status_counter[key.lower()] = recent.filter(status=key).count()

        periodic_total = PeriodicTask.objects.count()
        periodic_enabled = PeriodicTask.objects.filter(enabled=True).count()

        latest_tasks = list(
            TaskResult.objects.order_by("-date_done")
            .values("task_id", "task_name", "status", "date_done", "result", "traceback")[:20]
        )
        payload = {
            "summary": {
                "window_hours": 24,
                "total_recent": recent.count(),
                "status_counter": status_counter,
                "periodic_total": periodic_total,
                "periodic_enabled": periodic_enabled,
            },
            "recent_tasks": latest_tasks,
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminRoleListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        rows = AdminRole.objects.all().order_by("name", "id")
        payload = AdminRoleSerializer(rows, many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request):
        serializer = AdminRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        payload = serializer.data
        write_audit_log(request, action="admin.rbac.role.create", resource_type="role", resource_id=str(payload["id"]), status_code=201)
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminRoleDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def patch(self, request, role_id: int):
        row = get_object_or_404(AdminRole, pk=role_id)
        serializer = AdminRoleSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        payload = serializer.data
        write_audit_log(request, action="admin.rbac.role.update", resource_type="role", resource_id=str(row.id), status_code=200)
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminPermissionListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        rows = AdminPermission.objects.all().order_by("permission_type", "code", "id")
        payload = AdminPermissionSerializer(rows, many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request):
        serializer = AdminPermissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        payload = serializer.data
        write_audit_log(
            request,
            action="admin.rbac.permission.create",
            resource_type="permission",
            resource_id=str(payload["id"]),
            status_code=201,
        )
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminRolePermissionAssignView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, role_id: int):
        role = get_object_or_404(AdminRole, pk=role_id)
        codes = list(
            AdminRolePermission.objects.filter(role=role)
            .select_related("permission")
            .values_list("permission__code", flat=True)
        )
        return success_response(
            {"role_id": role.id, "permission_codes": codes},
            msg="success",
            code=0,
            status_code=status.HTTP_200_OK,
        )

    @transaction.atomic
    def post(self, request, role_id: int):
        role = get_object_or_404(AdminRole, pk=role_id)
        serializer = AdminRolePermissionAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        codes = serializer.validated_data["permission_codes"]
        rows = list(AdminPermission.objects.filter(code__in=codes))
        mapping = {row.code: row for row in rows}

        AdminRolePermission.objects.filter(role=role).exclude(permission__code__in=codes).delete()
        for code in codes:
            permission = mapping.get(code)
            if permission is None:
                continue
            AdminRolePermission.objects.get_or_create(role=role, permission=permission)

        payload = {"role_id": role.id, "permission_codes": codes}
        write_audit_log(request, action="admin.rbac.role.permission.assign", resource_type="role", resource_id=str(role.id), response_payload=payload)
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminUserRoleAssignView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:rbac:role:assign"

    @transaction.atomic
    def post(self, request, user_id: int):
        target = get_object_or_404(User, pk=user_id)
        serializer = AdminUserRoleAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        role_codes = serializer.validated_data["role_codes"]
        rows = list(AdminRole.objects.filter(code__in=role_codes))
        mapping = {row.code: row for row in rows}

        AdminUserRole.objects.filter(user=target).exclude(role__code__in=role_codes).delete()
        for code in role_codes:
            role = mapping.get(code)
            if role is None:
                continue
            AdminUserRole.objects.get_or_create(user=target, role=role)

        payload = {"user_id": target.id, "role_codes": role_codes}
        write_audit_log(
            request,
            action="admin.rbac.user.role.assign",
            resource_type="user",
            resource_id=str(target.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminAuditLogListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = AdminAuditLog.objects.select_related("user").all().order_by("-created_at", "-id")
        action = (request.query_params.get("action") or "").strip()
        if action:
            queryset = queryset.filter(action__icontains=action)

        status_code = (request.query_params.get("status_code") or "").strip()
        if status_code.isdigit():
            queryset = queryset.filter(status_code=int(status_code))

        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)

        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        payload = {
            "items": AdminAuditLogSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)
