"""快捷问题配置与生成记录后台接口（BACKOFFICE-CONVERSATION-000001）。"""

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.views import APIView

from common.permissions import SuperAdminOnlyPermission
from common.response import success_response
from medical.models import ChatGuideGeneratedQuestionRecord, ChatGuideQuickQuestionConfig

from backoffice.audit import write_audit_log
from backoffice.quick_question_serializers import (
    GeneratedQuestionRecordSerializer,
    QuickQuestionConfigCreateSerializer,
    QuickQuestionConfigSerializer,
    QuickQuestionConfigUpdateSerializer,
)


def _paginate(queryset, request, default_page_size: int = 20):
    page = max(int(request.query_params.get("page", "1")), 1)
    page_size = min(max(int(request.query_params.get("page_size", str(default_page_size))), 1), 100)
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)
    return page_obj, page_size, paginator


def _parse_dt(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _paginated_response(page_obj, page_size, paginator, items):
    return success_response(
        {
            "items": items,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        },
        msg="success",
        code=0,
        status_code=status.HTTP_200_OK,
    )


class AdminQuickQuestionConfigListCreateView(APIView):
    permission_classes = [SuperAdminOnlyPermission]

    def get(self, request):
        queryset = ChatGuideQuickQuestionConfig.objects.all()

        keyword = (request.query_params.get("keyword") or "").strip()
        if keyword:
            queryset = queryset.filter(Q(title__icontains=keyword) | Q(prompt__icontains=keyword))

        category = (request.query_params.get("category") or "").strip()
        if category:
            queryset = queryset.filter(category=category)

        locale = (request.query_params.get("locale") or "").strip()
        if locale:
            queryset = queryset.filter(locale=locale)

        is_active = request.query_params.get("is_active")
        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))

        queryset = queryset.order_by("-updated_at", "-id")
        page_obj, page_size, paginator = _paginate(queryset, request)

        write_audit_log(
            request,
            action="admin.conversation.quick_questions.configs.list",
            resource_type="quick_question_config",
            resource_id="list",
            status_code=200,
        )
        return _paginated_response(
            page_obj,
            page_size,
            paginator,
            QuickQuestionConfigSerializer(page_obj.object_list, many=True).data,
        )

    def post(self, request):
        serializer = QuickQuestionConfigCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config = serializer.save(created_by=request.user)

        write_audit_log(
            request,
            action="admin.conversation.quick_questions.configs.create",
            resource_type="quick_question_config",
            resource_id=str(config.id),
            status_code=201,
        )
        return success_response(
            QuickQuestionConfigSerializer(config).data,
            msg="created",
            code=0,
            status_code=status.HTTP_201_CREATED,
        )


class AdminQuickQuestionConfigDetailView(APIView):
    permission_classes = [SuperAdminOnlyPermission]

    def get(self, request, config_id: int):
        config = get_object_or_404(ChatGuideQuickQuestionConfig, pk=config_id)
        return success_response(
            QuickQuestionConfigSerializer(config).data,
            msg="success",
            code=0,
            status_code=status.HTTP_200_OK,
        )

    def patch(self, request, config_id: int):
        config = get_object_or_404(ChatGuideQuickQuestionConfig, pk=config_id)
        serializer = QuickQuestionConfigUpdateSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        config = serializer.save(updated_by=request.user)

        write_audit_log(
            request,
            action="admin.conversation.quick_questions.configs.update",
            resource_type="quick_question_config",
            resource_id=str(config.id),
            status_code=200,
        )
        return success_response(
            QuickQuestionConfigSerializer(config).data,
            msg="updated",
            code=0,
            status_code=status.HTTP_200_OK,
        )


class AdminQuickQuestionConfigEnableView(APIView):
    permission_classes = [SuperAdminOnlyPermission]

    def post(self, request, config_id: int):
        config = get_object_or_404(ChatGuideQuickQuestionConfig, pk=config_id)
        config.is_active = True
        config.updated_by = request.user
        config.save(update_fields=["is_active", "updated_by", "updated_at"])

        write_audit_log(
            request,
            action="admin.conversation.quick_questions.configs.enable",
            resource_type="quick_question_config",
            resource_id=str(config.id),
            status_code=200,
        )
        return success_response(
            QuickQuestionConfigSerializer(config).data,
            msg="enabled",
            code=0,
            status_code=status.HTTP_200_OK,
        )


class AdminQuickQuestionConfigDisableView(APIView):
    permission_classes = [SuperAdminOnlyPermission]

    def post(self, request, config_id: int):
        config = get_object_or_404(ChatGuideQuickQuestionConfig, pk=config_id)
        config.is_active = False
        config.updated_by = request.user
        config.save(update_fields=["is_active", "updated_by", "updated_at"])

        write_audit_log(
            request,
            action="admin.conversation.quick_questions.configs.disable",
            resource_type="quick_question_config",
            resource_id=str(config.id),
            status_code=200,
        )
        return success_response(
            QuickQuestionConfigSerializer(config).data,
            msg="disabled",
            code=0,
            status_code=status.HTTP_200_OK,
        )


class AdminGeneratedQuestionRecordListView(APIView):
    permission_classes = [SuperAdminOnlyPermission]

    def get(self, request):
        queryset = ChatGuideGeneratedQuestionRecord.objects.select_related("user", "member").all()

        keyword = (request.query_params.get("keyword") or "").strip()
        if keyword:
            queryset = queryset.filter(Q(title__icontains=keyword) | Q(prompt__icontains=keyword))

        user_id = (request.query_params.get("user_id") or "").strip()
        if user_id.isdigit():
            queryset = queryset.filter(user_id=int(user_id))

        member_id = (request.query_params.get("member_id") or "").strip()
        if member_id.isdigit():
            queryset = queryset.filter(member_id=int(member_id))

        category = (request.query_params.get("category") or "").strip()
        if category:
            queryset = queryset.filter(category=category)

        created_at_start = _parse_dt(request.query_params.get("created_at_start"))
        created_at_end = _parse_dt(request.query_params.get("created_at_end"))
        if created_at_start:
            queryset = queryset.filter(created_at__gte=created_at_start)
        if created_at_end:
            queryset = queryset.filter(created_at__lte=created_at_end)

        click_count_min = (request.query_params.get("click_count_min") or "").strip()
        click_count_max = (request.query_params.get("click_count_max") or "").strip()
        if click_count_min.isdigit():
            queryset = queryset.filter(click_count__gte=int(click_count_min))
        if click_count_max.isdigit():
            queryset = queryset.filter(click_count__lte=int(click_count_max))

        queryset = queryset.order_by("-created_at", "-id")
        page_obj, page_size, paginator = _paginate(queryset, request)

        write_audit_log(
            request,
            action="admin.conversation.quick_questions.generated_records.list",
            resource_type="quick_question_generated_record",
            resource_id="list",
            status_code=200,
        )
        return _paginated_response(
            page_obj,
            page_size,
            paginator,
            GeneratedQuestionRecordSerializer(page_obj.object_list, many=True).data,
        )


class AdminGeneratedQuestionRecordDetailView(APIView):
    permission_classes = [SuperAdminOnlyPermission]

    def get(self, request, record_id: int):
        record = get_object_or_404(
            ChatGuideGeneratedQuestionRecord.objects.select_related("user", "member"),
            pk=record_id,
        )
        return success_response(
            GeneratedQuestionRecordSerializer(record).data,
            msg="success",
            code=0,
            status_code=status.HTTP_200_OK,
        )