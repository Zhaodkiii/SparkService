from __future__ import annotations

import time
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView

from common.permissions import AdminCodePermission
from common.response import error_response, success_response
from file_manager.models import ManagedFile
from file_manager.url_utils import managed_file_download_url
from medical.models import (
    MedicationPlan,
    MedicationRecord,
    MedicineBox,
    Member,
    Prescription,
    UserMemberBinding,
)

from backoffice.audit import write_audit_log
from backoffice.medical_data_perf import paginate_params, success_with_meta, with_medical_data_perf
from backoffice.medical_data_serializers import (
    RESOURCE_TYPE_MAP,
    admin_can_download_attachment,
    admin_permissions_payload,
    build_timeline_events,
    compute_quality_flags,
    member_attachments_queryset,
    user_attachments_queryset,
    serialize_list_item,
    serialize_member_brief,
    serialize_resource_detail,
    serialize_shared_relations,
    serialize_user_medical_row,
    serialize_user_summary,
)
from backoffice.medical_data_stats_service import (
    get_global_stats,
    get_member_stats_row,
    get_user_stats_row,
    member_stats_dict,
)

User = get_user_model()

DATA_TYPE_FIELD_MAP = {
    "medical_case": "category_totals__medical_case",
    "health_exam": "category_totals__health_exam",
    "examination": "category_totals__examination",
    "medicine_box": "category_totals__medicine_box",
    "prescription": "category_totals__prescription",
    "medication_plan": "category_totals__medication_plan",
    "symptom": "category_totals__symptom",
    "visit": "category_totals__visit",
    "surgery": "category_totals__surgery",
    "follow_up": "category_totals__follow_up",
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _get_entry_binding(user_id: int, member_id: int) -> UserMemberBinding:
    binding = (
        UserMemberBinding.objects.filter(
            user_id=user_id,
            member_id=member_id,
            member__is_deleted=False,
        )
        .select_related("member")
        .order_by("-status", "-id")
        .first()
    )
    if binding is None:
        raise Member.DoesNotExist
    return binding


class AdminMedicalDataGlobalStatsView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "api:medical_data:user:list"

    @with_medical_data_perf
    def get(self, request):
        start = time.perf_counter()
        stats = get_global_stats(allow_refresh=True)
        duration_ms = int((time.perf_counter() - start) * 1000)
        return success_with_meta(
            {"stats": stats},
            duration_ms=duration_ms,
            cache_hit=stats.get("cache_hit", False),
            stats_status=stats.get("stats_status", "ready"),
        )


class AdminMedicalDataUserListView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "api:medical_data:user:list"

    @with_medical_data_perf
    def get(self, request):
        start = time.perf_counter()
        page, page_size = paginate_params(request)

        queryset = (
            User.objects.filter(medical_data_stats__members_with_data_count__gt=0)
            .select_related("medical_data_stats")
            .order_by("-medical_data_stats__last_medical_updated_at", "-id")
        )

        user_id = (request.query_params.get("user_id") or "").strip()
        if user_id.isdigit():
            queryset = queryset.filter(id=int(user_id))

        keyword = (request.query_params.get("keyword") or "").strip()
        if keyword:
            queryset = queryset.filter(Q(username__icontains=keyword) | Q(email__icontains=keyword))

        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter == "active":
            queryset = queryset.filter(is_active=True).exclude(username__startswith="deleted_user_")
        elif status_filter == "inactive":
            queryset = queryset.filter(is_active=False)
        elif status_filter == "deactivated":
            queryset = queryset.filter(Q(username__startswith="deleted_user_") | Q(email__endswith="@anonymized.local"))

        updated_after = _parse_dt(request.query_params.get("updated_after"))
        updated_before = _parse_dt(request.query_params.get("updated_before"))
        if updated_after:
            queryset = queryset.filter(medical_data_stats__last_medical_updated_at__gte=updated_after)
        if updated_before:
            queryset = queryset.filter(medical_data_stats__last_medical_updated_at__lte=updated_before)

        has_attachment = request.query_params.get("has_attachment")
        if has_attachment == "true":
            queryset = queryset.filter(medical_data_stats__attachment_count__gt=0)
        elif has_attachment == "false":
            queryset = queryset.filter(medical_data_stats__attachment_count=0)

        has_ai_task = request.query_params.get("has_ai_task")
        if has_ai_task == "true":
            queryset = queryset.filter(medical_data_stats__ai_task_count__gt=0)
        elif has_ai_task == "false":
            queryset = queryset.filter(medical_data_stats__ai_task_count=0)

        data_type = (request.query_params.get("data_type") or "").strip()
        if data_type in DATA_TYPE_FIELD_MAP:
            queryset = queryset.filter(**{f"{DATA_TYPE_FIELD_MAP[data_type]}__gt": 0})

        ordering = (request.query_params.get("ordering") or "-last_updated").strip()
        ordering_map = {
            "-last_updated": ("-medical_data_stats__last_medical_updated_at", "-id"),
            "last_updated": ("medical_data_stats__last_medical_updated_at", "id"),
            "-medical_data_total": ("-medical_data_stats__medical_data_total", "-id"),
            "medical_data_total": ("medical_data_stats__medical_data_total", "id"),
        }
        if ordering in ordering_map:
            queryset = queryset.order_by(*ordering_map[ordering])

        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        items = []
        for user in page_obj.object_list:
            stats_row = getattr(user, "medical_data_stats", None)
            if stats_row is None:
                stats_row = get_user_stats_row(user.id, allow_refresh=True)
            items.append(serialize_user_medical_row(user, admin_user=request.user, stats_row=stats_row))

        duration_ms = int((time.perf_counter() - start) * 1000)
        return success_with_meta(
            {
                "items": items,
                "pagination": {
                    "page": page_obj.number,
                    "page_size": page_size,
                    "total": paginator.count,
                    "total_pages": paginator.num_pages,
                },
                "permissions": admin_permissions_payload(request.user),
            },
            duration_ms=duration_ms,
            stats_status="ready",
        )


class AdminMedicalDataUserMembersView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "api:medical_data:member:list"

    @with_medical_data_perf
    def get(self, request, user_id: int):
        start = time.perf_counter()
        page, page_size = paginate_params(request)
        user = get_object_or_404(User, pk=user_id)
        stats_row = get_user_stats_row(user_id, allow_refresh=True)

        bindings_qs = (
            UserMemberBinding.objects.filter(
                user_id=user_id,
                status=UserMemberBinding.Status.ACTIVE,
                member__is_deleted=False,
            )
            .select_related("member")
            .order_by("-member__is_primary", "-member__updated_at", "-id")
        )

        # 默认展示全部绑定成员（含无医疗数据成员）；仅在有数据成员存在且显式 only_with_data 时过滤
        only_with_data = request.query_params.get("only_with_data") == "true"
        include_empty = request.query_params.get("include_empty")
        if include_empty == "false" or (include_empty is None and only_with_data):
            with_data_qs = bindings_qs.filter(member__admin_medical_stats__total_count__gt=0)
            if with_data_qs.exists():
                bindings_qs = with_data_qs

        paginator = Paginator(bindings_qs, page_size)
        page_obj = paginator.get_page(page)

        members = []
        for binding in page_obj.object_list:
            member_stats = get_member_stats_row(binding.member_id, allow_refresh=False)
            members.append(
                serialize_member_brief(
                    binding.member,
                    binding,
                    admin_user=request.user,
                    stats_payload=member_stats_dict(member_stats),
                )
            )

        write_audit_log(
            request,
            action="admin.medical_data.user.members.view",
            resource_type="user",
            resource_id=str(user_id),
        )

        duration_ms = int((time.perf_counter() - start) * 1000)
        return success_with_meta(
            {
                "user": serialize_user_summary(user, admin_user=request.user, stats_row=stats_row),
                "members": members,
                "pagination": {
                    "page": page_obj.number,
                    "page_size": page_size,
                    "total": paginator.count,
                    "total_pages": paginator.num_pages,
                },
                "permissions": admin_permissions_payload(request.user),
            },
            duration_ms=duration_ms,
            stats_status=getattr(stats_row, "refresh_status", "ready") if stats_row else "ready",
        )


class AdminMedicalDataMemberCompleteDataView(APIView):
    """轻量总览：仅摘要、分类计数、权限；不含时间线/完整异常/共享明细。"""

    permission_classes = [AdminCodePermission]
    required_permission_code = "api:medical_data:member:complete"

    @with_medical_data_perf
    def get(self, request, user_id: int, member_id: int):
        start = time.perf_counter()
        user = get_object_or_404(User, pk=user_id)
        try:
            binding = _get_entry_binding(user_id, member_id)
        except Member.DoesNotExist:
            return error_response(msg="member_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        member = binding.member
        member_stats = get_member_stats_row(member.id, allow_refresh=True)
        stats_payload = member_stats_dict(member_stats)
        entry_attachment_count = user_attachments_queryset(user_id=user.id).count()
        shared_count = UserMemberBinding.objects.filter(
            member_id=member.id,
            status=UserMemberBinding.Status.ACTIVE,
        ).count()

        write_audit_log(
            request,
            action="admin.medical_data.member.complete.view",
            resource_type="member",
            resource_id=str(member_id),
            response_payload={"entry_user_id": user_id},
        )

        duration_ms = int((time.perf_counter() - start) * 1000)
        return success_with_meta(
            {
                "member_id": member.id,
                "entry_user_id": user.id,
                "member": serialize_member_brief(
                    member,
                    binding,
                    admin_user=request.user,
                    stats_payload=stats_payload,
                ),
                "category_counts": {
                    "medical_cases": member_stats.medical_case_count,
                    "health_exam_reports": member_stats.health_exam_report_count,
                    "examination_reports": member_stats.examination_report_count,
                    "medicine_boxes": member_stats.medicine_box_count,
                    "prescriptions": member_stats.prescription_count,
                    "medication_plans": member_stats.medication_plan_count,
                    "symptoms": member_stats.symptom_count,
                    "visits": member_stats.visit_count,
                    "surgeries": member_stats.surgery_count,
                    "follow_ups": member_stats.follow_up_count,
                    "attachments": entry_attachment_count,
                },
                "medication_summary": stats_payload["medication_summary"],
                "source_summary": {
                    "manual": member_stats.manual_source_count,
                    "ai": member_stats.ai_recognition_count,
                },
                "ai_task_summary": {
                    "attachment_total": entry_attachment_count,
                    "ai_recognition_count": member_stats.ai_recognition_count,
                    "pending": member_stats.ai_pending_count,
                    "completed": member_stats.ai_recognition_count,
                },
                "quality_flag_count": member_stats.quality_flag_count,
                "shared_relations_summary": {
                    "active_binding_count": shared_count,
                },
                "permissions": admin_permissions_payload(request.user),
            },
            duration_ms=duration_ms,
            stats_status=member_stats.refresh_status,
            cache_hit=member_stats.refresh_status == member_stats.RefreshStatus.READY,
        )


class AdminMedicalDataMemberTimelineView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "api:medical_data:member:complete"

    @with_medical_data_perf
    def get(self, request, user_id: int, member_id: int):
        start = time.perf_counter()
        get_object_or_404(User, pk=user_id)
        try:
            _get_entry_binding(user_id, member_id)
        except Member.DoesNotExist:
            return error_response(msg="member_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        limit = min(max(int(request.query_params.get("limit", "30")), 1), 100)
        page, page_size = paginate_params(request, default_page_size=limit)
        events = build_timeline_events(member_id, limit=page_size * page)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        items = events[start_idx:end_idx]

        duration_ms = int((time.perf_counter() - start) * 1000)
        return success_with_meta(
            {
                "items": items,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": len(events),
                    "total_pages": max(1, (len(events) + page_size - 1) // page_size),
                },
            },
            duration_ms=duration_ms,
        )


class AdminMedicalDataMemberQualityFlagsView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "api:medical_data:member:complete"

    @with_medical_data_perf
    def get(self, request, user_id: int, member_id: int):
        start = time.perf_counter()
        get_object_or_404(User, pk=user_id)
        try:
            _get_entry_binding(user_id, member_id)
        except Member.DoesNotExist:
            return error_response(msg="member_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        flags = compute_quality_flags(member_id)
        page, page_size = paginate_params(request)
        paginator = Paginator(flags, page_size)
        page_obj = paginator.get_page(page)

        duration_ms = int((time.perf_counter() - start) * 1000)
        return success_with_meta(
            {
                "items": list(page_obj.object_list),
                "pagination": {
                    "page": page_obj.number,
                    "page_size": page_size,
                    "total": paginator.count,
                    "total_pages": paginator.num_pages,
                },
            },
            duration_ms=duration_ms,
        )


class AdminMedicalDataSharedRelationsView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "api:medical_data:member:list"

    @with_medical_data_perf
    def get(self, request, user_id: int, member_id: int):
        start = time.perf_counter()
        get_object_or_404(User, pk=user_id)
        try:
            _get_entry_binding(user_id, member_id)
        except Member.DoesNotExist:
            return error_response(msg="member_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        include_history = request.query_params.get("include_history") == "true"
        queryset = UserMemberBinding.objects.filter(member_id=member_id).select_related("user")
        if not include_history:
            queryset = queryset.filter(status=UserMemberBinding.Status.ACTIVE)

        page, page_size = paginate_params(request)
        ordered = list(queryset.order_by("-status", "-created_at", "-id"))
        paginator = Paginator(ordered, page_size)
        page_obj = paginator.get_page(page)
        page_member_ids = [b.member_id for b in page_obj.object_list]

        write_audit_log(
            request,
            action="admin.medical_data.member.shared_relations.view",
            resource_type="member",
            resource_id=str(member_id),
        )
        all_rows = serialize_shared_relations(member_id, admin_user=request.user)
        if not include_history:
            all_rows = [row for row in all_rows if row["status"] == UserMemberBinding.Status.ACTIVE]
        duration_ms = int((time.perf_counter() - start) * 1000)
        return success_with_meta(
            {
                "items": all_rows,
                "pagination": {
                    "page": page_obj.number,
                    "page_size": page_size,
                    "total": paginator.count,
                    "total_pages": paginator.num_pages,
                },
            },
            duration_ms=duration_ms,
        )


class AdminMedicalDataResourceListView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "api:medical_data:member:complete"

    @with_medical_data_perf
    def get(self, request, user_id: int, member_id: int, resource_type: str):
        start = time.perf_counter()
        if resource_type not in RESOURCE_TYPE_MAP and resource_type != "attachments":
            return error_response(msg="invalid_resource_type", code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        get_object_or_404(User, pk=user_id)
        try:
            binding = _get_entry_binding(user_id, member_id)
        except Member.DoesNotExist:
            return error_response(msg="member_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        member = binding.member

        if resource_type == "attachments":
            queryset = user_attachments_queryset(user_id=user_id)
        elif resource_type == "family-medicine-boxes":
            queryset = MedicineBox.objects.filter(user_id=user_id, is_deleted=False, member__isnull=True).order_by(
                "-updated_at", "-id"
            )
        elif resource_type == "medicine-boxes":
            queryset = MedicineBox.objects.filter(member_id=member.id, is_deleted=False).order_by("-updated_at", "-id")
        elif resource_type == "medication-records":
            queryset = MedicationRecord.objects.filter(member_id=member.id, is_deleted=False).order_by(
                "-scheduled_at", "-id"
            )
        else:
            _, model, _, _ = RESOURCE_TYPE_MAP[resource_type]
            queryset = model.objects.filter(member_id=member.id, is_deleted=False).order_by("-updated_at", "-id")

        keyword = (request.query_params.get("keyword") or "").strip()
        if keyword and resource_type != "attachments":
            if resource_type == "medical-cases":
                queryset = queryset.filter(Q(title__icontains=keyword) | Q(diagnosis_summary__icontains=keyword))
            elif resource_type in {"health-exam-reports"}:
                queryset = queryset.filter(Q(institution_name__icontains=keyword) | Q(summary__icontains=keyword))
            elif resource_type == "examination-reports":
                queryset = queryset.filter(Q(item_name__icontains=keyword) | Q(organization_name__icontains=keyword))
            elif resource_type in {"medicine-boxes", "family-medicine-boxes"}:
                queryset = queryset.filter(Q(medicine_name__icontains=keyword) | Q(brand_name__icontains=keyword))
            elif resource_type == "medication-plans":
                queryset = queryset.filter(Q(drug_name__icontains=keyword) | Q(frequency_text__icontains=keyword))

        page, page_size = paginate_params(request)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        items = [serialize_list_item(resource_type, obj, admin_user=request.user) for obj in page_obj.object_list]

        duration_ms = int((time.perf_counter() - start) * 1000)
        return success_with_meta(
            {
                "resource_type": resource_type,
                "member_id": member.id,
                "items": items,
                "pagination": {
                    "page": page_obj.number,
                    "page_size": page_size,
                    "total": paginator.count,
                    "total_pages": paginator.num_pages,
                },
                "permissions": admin_permissions_payload(request.user),
            },
            duration_ms=duration_ms,
        )


class AdminMedicalDataResourceDetailView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "api:medical_data:resource:detail"

    @with_medical_data_perf
    def get(self, request, resource_type: str, resource_id: int):
        if resource_type == "attachments":
            obj = get_object_or_404(ManagedFile, pk=resource_id, is_deleted=False)
        elif resource_type not in RESOURCE_TYPE_MAP:
            return error_response(msg="invalid_resource_type", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        else:
            _, model, _, _ = RESOURCE_TYPE_MAP[resource_type]
            obj = get_object_or_404(model, pk=resource_id, is_deleted=False)

        payload = serialize_resource_detail(resource_type, obj, admin_user=request.user)
        write_audit_log(
            request,
            action="admin.medical_data.resource.detail.view",
            resource_type=resource_type,
            resource_id=str(resource_id),
        )
        if payload.get("raw_json") is not None:
            write_audit_log(
                request,
                action="admin.medical_data.raw_json.view",
                resource_type=resource_type,
                resource_id=str(resource_id),
            )
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminMedicalDataAttachmentDownloadView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "api:medical_data:resource:detail"

    @with_medical_data_perf
    def get(self, request, file_id: int):
        if not admin_can_download_attachment(request.user):
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)

        file_record = get_object_or_404(ManagedFile, pk=file_id, is_deleted=False)
        url = managed_file_download_url(file_record)
        if not url:
            return error_response(msg="file_url_unavailable", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        write_audit_log(
            request,
            action="admin.medical_data.attachment.download",
            resource_type="attachment",
            resource_id=str(file_id),
        )
        return success_response(
            {"url": url, "expires_in_seconds": 3600, "file_id": file_id},
            msg="success",
            code=0,
            status_code=status.HTTP_200_OK,
        )
