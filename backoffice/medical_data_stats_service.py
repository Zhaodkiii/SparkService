from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from backoffice.models import MedicalDataGlobalStatsSnapshot, MedicalDataMemberStats, MedicalDataUserStats
from backoffice.medical_data_serializers import compute_member_stats, compute_quality_flags, compute_user_medical_stats
from medical.models import UserMemberBinding

User = get_user_model()
logger = logging.getLogger(__name__)

STATS_TTL_SECONDS = 300
GLOBAL_STATS_TTL_SECONDS = 120

CATEGORY_KEYS = (
    "medical_case",
    "health_exam",
    "examination",
    "medicine_box",
    "prescription",
    "medication_plan",
    "symptom",
    "visit",
    "surgery",
    "follow_up",
)


def _is_stale(refreshed_at, ttl_seconds: int) -> bool:
    if refreshed_at is None:
        return True
    return timezone.now() - refreshed_at > timedelta(seconds=ttl_seconds)


def member_stats_dict(row: MedicalDataMemberStats) -> dict:
    pending = max(row.today_medication_total - row.today_medication_taken - row.today_medication_skipped, 0)
    return {
        "medical_case_count": row.medical_case_count,
        "health_exam_report_count": row.health_exam_report_count,
        "examination_report_count": row.examination_report_count,
        "medicine_box_count": row.medicine_box_count,
        "prescription_count": row.prescription_count,
        "medication_plan_count": row.medication_plan_count,
        "symptom_count": row.symptom_count,
        "visit_count": row.visit_count,
        "surgery_count": row.surgery_count,
        "follow_up_count": row.follow_up_count,
        "attachment_count": row.attachment_count,
        "total_count": row.total_count,
        "has_data": row.total_count > 0,
        "last_updated_at": row.last_medical_updated_at,
        "medication_summary": {
            "today_total": row.today_medication_total,
            "today_taken": row.today_medication_taken,
            "today_skipped": row.today_medication_skipped,
            "today_pending": pending,
            "adherence_rate": float(row.adherence_rate),
        },
        "quality_flag_count": row.quality_flag_count,
        "ai_recognition_count": row.ai_recognition_count,
        "ai_pending_count": row.ai_pending_count,
        "stats_status": row.refresh_status,
        "refreshed_at": row.refreshed_at,
    }


def user_stats_dict(row: MedicalDataUserStats) -> dict:
    return {
        "member_count": row.member_count,
        "members_with_data_count": row.members_with_data_count,
        "medical_data_total": row.medical_data_total,
        "attachment_count": row.attachment_count,
        "ai_task_count": row.ai_task_count,
        "quality_flag_count": row.quality_flag_count,
        "category_totals": row.category_totals or {},
        "last_updated_at": row.last_medical_updated_at,
        "last_source": row.last_source,
        "stats_status": row.refresh_status,
        "refreshed_at": row.refreshed_at,
    }


@transaction.atomic
def refresh_member_stats(member_id: int) -> MedicalDataMemberStats:
    stats = compute_member_stats(member_id)
    quality_flags = compute_quality_flags(member_id)
    from medical.models import ExaminationReport, HealthExamReport, MedicalCase

    ai_count = (
        HealthExamReport.objects.filter(member_id=member_id, is_deleted=False, source=HealthExamReport.Source.OCR).count()
        + ExaminationReport.objects.filter(
            member_id=member_id, is_deleted=False, source=ExaminationReport.Source.OCR
        ).count()
    )
    ai_pending = HealthExamReport.objects.filter(
        member_id=member_id,
        is_deleted=False,
        source=HealthExamReport.Source.OCR,
        status=HealthExamReport.Status.DRAFT,
    ).count()
    manual_count = MedicalCase.objects.filter(member_id=member_id, is_deleted=False).count()

    medication = stats["medication_summary"]
    row, _ = MedicalDataMemberStats.objects.select_for_update().get_or_create(member_id=member_id)
    row.medical_case_count = stats["medical_case_count"]
    row.health_exam_report_count = stats["health_exam_report_count"]
    row.examination_report_count = stats["examination_report_count"]
    row.medicine_box_count = stats["medicine_box_count"]
    row.prescription_count = stats["prescription_count"]
    row.medication_plan_count = stats["medication_plan_count"]
    row.symptom_count = stats["symptom_count"]
    row.visit_count = stats["visit_count"]
    row.surgery_count = stats["surgery_count"]
    row.follow_up_count = stats["follow_up_count"]
    row.attachment_count = stats["attachment_count"]
    row.total_count = stats["total_count"]
    row.ai_recognition_count = ai_count
    row.ai_pending_count = ai_pending
    row.manual_source_count = manual_count
    row.quality_flag_count = len(quality_flags)
    row.today_medication_total = medication["today_total"]
    row.today_medication_taken = medication["today_taken"]
    row.today_medication_skipped = medication["today_skipped"]
    row.adherence_rate = medication["adherence_rate"]
    row.last_medical_updated_at = stats["last_updated_at"]
    row.refresh_status = MedicalDataMemberStats.RefreshStatus.READY
    row.refreshed_at = timezone.now()
    row.save()
    return row


@transaction.atomic
def refresh_user_stats(user_id: int) -> MedicalDataUserStats:
    member_ids = list(
        UserMemberBinding.objects.filter(
            user_id=user_id,
            status=UserMemberBinding.Status.ACTIVE,
            member__is_deleted=False,
        ).values_list("member_id", flat=True)
    )

    category_totals = {key: 0 for key in CATEGORY_KEYS}
    members_with_data = 0
    total = 0
    attachment_count = 0
    ai_task_count = 0
    quality_flag_count = 0
    last_updated_at = None

    for member_id in member_ids:
        member_row = get_member_stats_row(member_id, allow_refresh=True)
        if member_row.total_count > 0:
            members_with_data += 1
        total += member_row.total_count
        attachment_count += member_row.attachment_count
        ai_task_count += member_row.ai_recognition_count
        quality_flag_count += member_row.quality_flag_count
        category_totals["medical_case"] += member_row.medical_case_count
        category_totals["health_exam"] += member_row.health_exam_report_count
        category_totals["examination"] += member_row.examination_report_count
        category_totals["medicine_box"] += member_row.medicine_box_count
        category_totals["prescription"] += member_row.prescription_count
        category_totals["medication_plan"] += member_row.medication_plan_count
        category_totals["symptom"] += member_row.symptom_count
        category_totals["visit"] += member_row.visit_count
        category_totals["surgery"] += member_row.surgery_count
        category_totals["follow_up"] += member_row.follow_up_count
        if member_row.last_medical_updated_at and (
            last_updated_at is None or member_row.last_medical_updated_at > last_updated_at
        ):
            last_updated_at = member_row.last_medical_updated_at

    row, _ = MedicalDataUserStats.objects.select_for_update().get_or_create(user_id=user_id)
    row.member_count = len(member_ids)
    row.members_with_data_count = members_with_data
    row.medical_data_total = total
    row.attachment_count = attachment_count
    row.ai_task_count = ai_task_count
    row.quality_flag_count = quality_flag_count
    row.category_totals = category_totals
    row.last_medical_updated_at = last_updated_at
    row.last_source = "AI 识别" if ai_task_count > 0 else ""
    row.refresh_status = MedicalDataUserStats.RefreshStatus.READY
    row.refreshed_at = timezone.now()
    row.save()
    return row


@transaction.atomic
def refresh_global_stats() -> MedicalDataGlobalStatsSnapshot:
    users_with_data = MedicalDataUserStats.objects.filter(members_with_data_count__gt=0).count()
    users_with_ai = MedicalDataUserStats.objects.filter(ai_task_count__gt=0).count()
    aggregates = MedicalDataUserStats.objects.aggregate(
        medical_data_total=Sum("medical_data_total"),
        attachment_total=Sum("attachment_count"),
    )
    row, _ = MedicalDataGlobalStatsSnapshot.objects.select_for_update().get_or_create(key="global")
    row.users_with_medical_data = users_with_data
    row.users_with_ai_recognition = users_with_ai
    row.medical_data_total = aggregates["medical_data_total"] or 0
    row.attachment_total = aggregates["attachment_total"] or 0
    row.refresh_status = MedicalDataGlobalStatsSnapshot.RefreshStatus.READY
    row.refreshed_at = timezone.now()
    row.save()
    return row


def get_member_stats_row(member_id: int, *, allow_refresh: bool = True) -> MedicalDataMemberStats:
    row = MedicalDataMemberStats.objects.filter(member_id=member_id).first()
    if row is None:
        return refresh_member_stats(member_id)
    if allow_refresh and _is_stale(row.refreshed_at, STATS_TTL_SECONDS):
        try:
            return refresh_member_stats(member_id)
        except Exception:
            logger.exception("refresh_member_stats failed member_id=%s", member_id)
            MedicalDataMemberStats.objects.filter(pk=row.pk).update(
                refresh_status=MedicalDataMemberStats.RefreshStatus.STALE
            )
            row.refresh_status = MedicalDataMemberStats.RefreshStatus.STALE
    return row


def get_user_stats_row(user_id: int, *, allow_refresh: bool = True) -> MedicalDataUserStats | None:
    row = MedicalDataUserStats.objects.filter(user_id=user_id).first()
    if row is None:
        stats = compute_user_medical_stats(user_id)
        if stats["members_with_data_count"] == 0 and stats["member_count"] == 0:
            return None
        return refresh_user_stats(user_id)
    if allow_refresh and _is_stale(row.refreshed_at, STATS_TTL_SECONDS):
        try:
            return refresh_user_stats(user_id)
        except Exception:
            logger.exception("refresh_user_stats failed user_id=%s", user_id)
            MedicalDataUserStats.objects.filter(pk=row.pk).update(
                refresh_status=MedicalDataUserStats.RefreshStatus.STALE
            )
            row.refresh_status = MedicalDataUserStats.RefreshStatus.STALE
    return row


def get_global_stats(*, allow_refresh: bool = True) -> dict:
    row = MedicalDataGlobalStatsSnapshot.objects.filter(key="global").first()
    if row is None or (allow_refresh and _is_stale(row.refreshed_at, GLOBAL_STATS_TTL_SECONDS)):
        try:
            row = refresh_global_stats()
            cache_hit = False
        except Exception:
            logger.exception("refresh_global_stats failed")
            if row is None:
                return {
                    "users_with_medical_data": 0,
                    "users_with_ai_recognition": 0,
                    "medical_data_total": 0,
                    "attachment_total": 0,
                    "stats_status": "stale",
                    "cache_hit": False,
                }
            cache_hit = True
    else:
        cache_hit = True

    return {
        "users_with_medical_data": row.users_with_medical_data,
        "users_with_ai_recognition": row.users_with_ai_recognition,
        "medical_data_total": row.medical_data_total,
        "attachment_total": row.attachment_total,
        "stats_status": row.refresh_status,
        "refreshed_at": row.refreshed_at,
        "cache_hit": cache_hit,
    }


def ensure_user_stats_for_users(user_ids: list[int]) -> dict[int, MedicalDataUserStats]:
    rows = {
        row.user_id: row
        for row in MedicalDataUserStats.objects.filter(user_id__in=user_ids)
    }
    for user_id in user_ids:
        if user_id not in rows:
            refreshed = get_user_stats_row(user_id, allow_refresh=True)
            if refreshed is not None:
                rows[user_id] = refreshed
    return rows


def mark_member_stats_stale(member_id: int) -> None:
    MedicalDataMemberStats.objects.filter(member_id=member_id).update(
        refresh_status=MedicalDataMemberStats.RefreshStatus.STALE
    )


def mark_user_stats_stale(user_id: int) -> None:
    MedicalDataUserStats.objects.filter(user_id=user_id).update(
        refresh_status=MedicalDataUserStats.RefreshStatus.STALE
    )
