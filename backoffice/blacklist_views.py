from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView

from accounts.models import AccessDenyEntry
from accounts.services.access_control_service import AccessControlService
from backoffice.audit import write_audit_log
from backoffice.serializers import AdminAccessDenyCreateSerializer, AdminAccessDenyEntrySerializer
from common.exceptions import APIError
from common.permissions import AdminCodePermission
from common.response import success_response

User = get_user_model()


class AdminAccessDenyListCreateView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:user:blacklist:manage"

    def get(self, request):
        queryset = AccessDenyEntry.objects.all().order_by("-created_at", "-id")
        active_only = (request.query_params.get("active_only") or "").strip().lower()
        if active_only in {"1", "true", "yes"}:
            now = timezone.now()
            queryset = queryset.filter(revoked_at__isnull=True).filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now)
            )
        dimension = (request.query_params.get("dimension") or "").strip()
        if dimension:
            queryset = queryset.filter(dimension=dimension)
        q = (request.query_params.get("q") or "").strip()
        if q:
            filters = Q(dimension_value__icontains=q) | Q(reason_note__icontains=q)
            if q.isdigit():
                filters |= Q(related_user_id=int(q))
            queryset = queryset.filter(filters)

        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        payload = {
            "items": AdminAccessDenyEntrySerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request):
        serializer = AdminAccessDenyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        request_id = getattr(request, "request_id", "") or ""
        created_by_id = request.user.id

        try:
            if data.get("user_id"):
                target = User.objects.filter(id=data["user_id"]).first()
                if target is None:
                    raise APIError("user_not_found", code=40401, status_code=404)
                result = AccessControlService.ban_user(
                    user=target,
                    reason_note=data.get("reason_note", ""),
                    created_by_id=created_by_id,
                    request_id=request_id,
                    send_sms=True,
                )
            elif data.get("phone"):
                result = AccessControlService.ban_phone(
                    phone_number=data["phone"],
                    reason_note=data.get("reason_note", ""),
                    created_by_id=created_by_id,
                    request_id=request_id,
                )
            else:
                result = AccessControlService.ban_email(
                    email=data["email"],
                    reason_note=data.get("reason_note", ""),
                    created_by_id=created_by_id,
                    request_id=request_id,
                )
        except APIError as exc:
            write_audit_log(
                request,
                action="admin.user.blacklist.create.failed",
                resource_type="access_deny",
                status_code=exc.status_code,
            )
            raise

        entry = AccessDenyEntry.objects.filter(id=result["entry_id"]).first()
        payload = {
            "result": result,
            "entry": AdminAccessDenyEntrySerializer(entry).data if entry else None,
        }
        write_audit_log(
            request,
            action="admin.user.blacklist.create",
            resource_type="access_deny",
            resource_id=str(result.get("entry_id", "")),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_200_OK)


class AdminAccessDenyRevokeView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:user:blacklist:manage"

    def post(self, request, entry_id: int):
        entry = AccessControlService.revoke_entry(entry_id=entry_id, revoked_by_id=request.user.id)
        payload = AdminAccessDenyEntrySerializer(entry).data
        write_audit_log(
            request,
            action="admin.user.blacklist.revoke",
            resource_type="access_deny",
            resource_id=str(entry.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="revoked", code=0, status_code=status.HTTP_200_OK)
