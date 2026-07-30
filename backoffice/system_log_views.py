from django.core.paginator import Paginator
from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.views import APIView

from accounts.models import LoginAudit
from backoffice.audit import write_audit_log
from backoffice.serializers import AdminLoginAuditSerializer
from backoffice.system_logs.service import SystemLogQuery, SystemLogService
from common.exceptions import APIError
from common.permissions import AdminOnlyPermission
from common.response import success_response


class AdminSystemLogModuleListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        payload = SystemLogService.list_modules()
        write_audit_log(request, action="admin.audit.system.modules.view", resource_type="system_log")
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminSystemLogListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        date_value = (request.query_params.get("date") or "").strip()
        module = (request.query_params.get("module") or "access").strip()
        if not date_value:
            raise APIError("date_required", code=40076, status_code=400)
        if parse_date(date_value) is None:
            raise APIError("invalid_log_date", code=40072, status_code=400)

        query = SystemLogQuery(
            date=date_value,
            module=module,
            level=(request.query_params.get("level") or "").strip(),
            status=(request.query_params.get("status") or "").strip(),
            request_id=(request.query_params.get("request_id") or "").strip(),
            path=(request.query_params.get("path") or "").strip(),
            keyword=(request.query_params.get("keyword") or "").strip(),
            page=int(request.query_params.get("page", "1")),
            page_size=int(request.query_params.get("page_size", "50")),
            order=(request.query_params.get("order") or "desc").strip() or "desc",
        )
        payload = SystemLogService.query(query)
        write_audit_log(
            request,
            action="admin.audit.system.logs.view",
            resource_type="system_log",
            response_payload={"date": query.date, "module": query.module, "total": payload["pagination"]["total"]},
        )
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminSystemLogDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        date_value = (request.query_params.get("date") or "").strip()
        module = (request.query_params.get("module") or "").strip()
        line_no = int(request.query_params.get("line_no", "0"))
        if not date_value or not module or line_no < 1:
            raise APIError("invalid_detail_query", code=40077, status_code=400)

        payload = SystemLogService.detail(date=date_value, module=module, line_no=line_no)
        write_audit_log(
            request,
            action="admin.audit.system.log.detail",
            resource_type="system_log",
            resource_id=f"{payload.get('date')}:{payload.get('module')}:{payload.get('line_no')}",
        )
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminLoginAuditListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = LoginAudit.objects.select_related("user").all().order_by("-created_at", "-id")

        provider = (request.query_params.get("provider") or "").strip()
        outcome = (request.query_params.get("outcome") or "").strip()
        request_id = (request.query_params.get("request_id") or "").strip()
        bundle_id = (request.query_params.get("bundle_id") or "").strip()
        device_id = (request.query_params.get("device_id") or "").strip()
        keyword = (request.query_params.get("keyword") or "").strip()
        date_from = (request.query_params.get("date_from") or "").strip()
        date_to = (request.query_params.get("date_to") or "").strip()

        if provider:
            queryset = queryset.filter(provider=provider)
        if outcome:
            queryset = queryset.filter(outcome=outcome)
        if request_id:
            queryset = queryset.filter(request_id=request_id)
        if bundle_id:
            queryset = queryset.filter(bundle_id=bundle_id)
        if device_id:
            queryset = queryset.filter(device_id=device_id)
        if keyword:
            queryset = queryset.filter(
                Q(user_agent__icontains=keyword)
                | Q(raw_claims__icontains=keyword)
            )
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)
        page_obj = Paginator(queryset, page_size).get_page(page)

        payload = {
            "items": AdminLoginAuditSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": page_obj.paginator.count,
                "total_pages": page_obj.paginator.num_pages,
            },
        }
        write_audit_log(request, action="admin.audit.login.logs.view", resource_type="login_audit")
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)
