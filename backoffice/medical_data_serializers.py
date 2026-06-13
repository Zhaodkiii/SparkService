from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Q
from django.utils import timezone

from backoffice.conversation_serializers import format_user_display_name, format_user_status, is_anonymized_user
from file_manager.models import ManagedFile, ManagedFileBusinessRelation
from file_manager.serializers import ManagedFileAttachmentOutSerializer
from file_manager.url_utils import managed_file_download_url
from medical.models import (
    ExaminationReport,
    FollowUp,
    HealthExamReport,
    MedExamDetail,
    MedicalCase,
    MedicationPlan,
    MedicationRecord,
    MedicineBox,
    Member,
    Prescription,
    Surgery,
    Symptom,
    UserMemberBinding,
    Visit,
)
from medical.serializers import (
    ExaminationReportSerializer,
    FollowUpSerializer,
    HealthExamReportSerializer,
    MedicalCaseSerializer,
    MedicationPlanSerializer,
    MedicationRecordSerializer,
    MedicineBoxSerializer,
    PrescriptionSerializer,
    SurgerySerializer,
    SymptomSerializer,
    VisitSerializer,
)

User = get_user_model()

RELATIONSHIP_LABELS = {
    "self": "本人",
    "father": "父亲",
    "mother": "母亲",
    "spouse": "配偶",
    "child": "子女",
    "son": "儿子",
    "daughter": "女儿",
    "grandfather": "祖父",
    "grandmother": "祖母",
    "other": "其他",
}

SOURCE_LABELS = {
    1: "手动录入",
    2: "AI 识别",
    3: "导入",
}

ROLE_LABELS = {
    UserMemberBinding.Role.OWNER: "所有者",
    UserMemberBinding.Role.ADMIN: "管理员",
    UserMemberBinding.Role.EDITOR: "可编辑",
    UserMemberBinding.Role.VIEWER: "可查看",
}

STATUS_LABELS = {
    UserMemberBinding.Status.ACTIVE: "正常",
    UserMemberBinding.Status.REVOKED: "已解绑",
}

GENDER_LABELS = {
    Member.Gender.MALE: "男",
    Member.Gender.FEMALE: "女",
    Member.Gender.UNKNOWN: "未知",
}

RESOURCE_TYPE_MAP = {
    "medical-cases": ("medical_case", MedicalCase, MedicalCaseSerializer, "medical_cases"),
    "health-exam-reports": ("health_exam_report", HealthExamReport, HealthExamReportSerializer, "health_exam_reports"),
    "examination-reports": ("examination_report", ExaminationReport, ExaminationReportSerializer, "examination_reports"),
    "medicine-boxes": ("medicine_box", MedicineBox, MedicineBoxSerializer, "medicine_boxes"),
    "family-medicine-boxes": ("medicine_box", MedicineBox, MedicineBoxSerializer, "family_medicine_boxes"),
    "prescriptions": ("prescription_batch", Prescription, PrescriptionSerializer, "prescriptions"),
    "medication-plans": ("medication_plan", MedicationPlan, MedicationPlanSerializer, "medication_plans"),
    "medication-records": ("medication_record", MedicationRecord, MedicationRecordSerializer, "medication_records"),
    "symptoms": ("symptom", Symptom, SymptomSerializer, "symptoms"),
    "visits": ("visit", Visit, VisitSerializer, "visits"),
    "surgeries": ("surgery", Surgery, SurgerySerializer, "surgeries"),
    "follow-ups": ("follow_up", FollowUp, FollowUpSerializer, "follow_ups"),
}


def format_relationship(value: str | None) -> str:
    key = (value or "self").strip().lower()
    return RELATIONSHIP_LABELS.get(key, value or "本人")


def format_gender(value: str | None) -> str:
    key = (value or Member.Gender.UNKNOWN).strip().lower()
    return GENDER_LABELS.get(key, "未知")


def format_source(value: int | None) -> str:
    if value is None:
        return "未知"
    return SOURCE_LABELS.get(int(value), f"来源{value}")


def mask_email(email: str, *, reveal: bool) -> str:
    text = (email or "").strip()
    if not text:
        return ""
    if reveal or is_anonymized_user_type(text):
        return text
    if "@" not in text:
        return text[:1] + "***"
    local, domain = text.split("@", 1)
    masked_local = (local[:1] + "***") if local else "***"
    return f"{masked_local}@{domain}"


def is_anonymized_user_type(text: str) -> bool:
    return text.endswith("@anonymized.local") or text.startswith("deleted_user_")


def mask_phone(phone: str, *, reveal: bool) -> str:
    text = (phone or "").strip()
    if not text:
        return ""
    if reveal:
        return text
    if len(text) <= 4:
        return "***"
    return text[:3] + "****" + text[-2:]


def mask_name(name: str, *, reveal: bool) -> str:
    text = (name or "").strip()
    if not text:
        return ""
    if reveal:
        return text
    if len(text) == 1:
        return text + "*"
    return text[:1] + "**"


def mask_text(text: str, *, reveal: bool, limit: int = 80) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    if reveal:
        return value
    if len(value) <= 8:
        return value[:2] + "***"
    return value[:4] + "…" + value[-2:]


def admin_can_view_sensitive(admin_user) -> bool:
    if getattr(admin_user, "is_superuser", False):
        return True
    from backoffice.rbac import has_permission_code

    return has_permission_code(admin_user.id, "button:medical_data:sensitive:view")


def admin_can_view_raw_json(admin_user) -> bool:
    if getattr(admin_user, "is_superuser", False):
        return True
    from backoffice.rbac import has_permission_code

    return has_permission_code(admin_user.id, "button:medical_data:raw_json:view")


def admin_can_view_attachment(admin_user) -> bool:
    if getattr(admin_user, "is_superuser", False):
        return True
    from backoffice.rbac import has_permission_code

    return has_permission_code(admin_user.id, "button:medical_data:attachment:view")


def admin_can_download_attachment(admin_user) -> bool:
    if getattr(admin_user, "is_superuser", False):
        return True
    from backoffice.rbac import has_permission_code

    return has_permission_code(admin_user.id, "button:medical_data:attachment:download")


def admin_permissions_payload(admin_user) -> dict:
    return {
        "can_view_sensitive": admin_can_view_sensitive(admin_user),
        "can_view_raw_json": admin_can_view_raw_json(admin_user),
        "can_view_attachment": admin_can_view_attachment(admin_user),
        "can_download_attachment": admin_can_download_attachment(admin_user),
    }


def _member_ids_for_user(user_id: int) -> list[int]:
    return list(
        UserMemberBinding.objects.filter(
            user_id=user_id,
            status=UserMemberBinding.Status.ACTIVE,
            member__is_deleted=False,
        )
        .values_list("member_id", flat=True)
        .distinct()
    )


def compute_member_stats(member_id: int) -> dict:
    today = timezone.localdate()
    stats = {
        "medical_case_count": MedicalCase.objects.filter(member_id=member_id, is_deleted=False).count(),
        "health_exam_report_count": HealthExamReport.objects.filter(member_id=member_id, is_deleted=False).count(),
        "examination_report_count": ExaminationReport.objects.filter(member_id=member_id, is_deleted=False).count(),
        "medicine_box_count": MedicineBox.objects.filter(member_id=member_id, is_deleted=False).count(),
        "prescription_count": Prescription.objects.filter(member_id=member_id, is_deleted=False).count(),
        "medication_plan_count": MedicationPlan.objects.filter(member_id=member_id, is_deleted=False).count(),
        "symptom_count": Symptom.objects.filter(member_id=member_id, is_deleted=False).count(),
        "visit_count": Visit.objects.filter(member_id=member_id, is_deleted=False).count(),
        "surgery_count": Surgery.objects.filter(member_id=member_id, is_deleted=False).count(),
        "follow_up_count": FollowUp.objects.filter(member_id=member_id, is_deleted=False).count(),
    }
    owner_user_id = (
        Member.objects.filter(id=member_id, is_deleted=False).values_list("user_id", flat=True).first()
    )
    stats["attachment_count"] = (
        user_attachments_queryset(user_id=owner_user_id).count()
        if owner_user_id
        else 0
    )
    stats["total_count"] = sum(
        stats[key]
        for key in (
            "medical_case_count",
            "health_exam_report_count",
            "examination_report_count",
            "medicine_box_count",
            "prescription_count",
            "medication_plan_count",
            "symptom_count",
            "visit_count",
            "surgery_count",
            "follow_up_count",
        )
    )
    stats["has_data"] = stats["total_count"] > 0

    latest_candidates = []
    for model in (
        MedicalCase,
        HealthExamReport,
        ExaminationReport,
        MedicineBox,
        Prescription,
        MedicationPlan,
        Symptom,
        Visit,
        Surgery,
        FollowUp,
    ):
        latest = (
            model.objects.filter(member_id=member_id, is_deleted=False)
            .order_by("-updated_at")
            .values_list("updated_at", flat=True)
            .first()
        )
        if latest:
            latest_candidates.append(latest)
    stats["last_updated_at"] = max(latest_candidates) if latest_candidates else None

    today_records = MedicationRecord.objects.filter(
        member_id=member_id,
        is_deleted=False,
        scheduled_at__date=today,
    )
    today_total = today_records.count()
    today_taken = today_records.filter(status=MedicationRecord.Status.TAKEN).count()
    today_skipped = today_records.filter(status=MedicationRecord.Status.SKIPPED).count()
    stats["medication_summary"] = {
        "today_total": today_total,
        "today_taken": today_taken,
        "today_skipped": today_skipped,
        "today_pending": max(today_total - today_taken - today_skipped, 0),
        "adherence_rate": round((today_taken / today_total) * 100, 2) if today_total else 0,
    }
    return stats


MEMBER_ATTACHMENT_MODELS: tuple[tuple[str, type], ...] = (
    ("medical_case", MedicalCase),
    ("health_exam_report", HealthExamReport),
    ("examination_report", ExaminationReport),
    ("medicine_box", MedicineBox),
    ("prescription_batch", Prescription),
    ("medication_plan", MedicationPlan),
    ("medication_record", MedicationRecord),
    ("symptom", Symptom),
    ("visit", Visit),
    ("surgery", Surgery),
    ("follow_up", FollowUp),
)


def _business_refs_for_member(member_id: int) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for business_type, model in MEMBER_ATTACHMENT_MODELS:
        for pk in model.objects.filter(member_id=member_id, is_deleted=False).values_list("id", flat=True):
            refs.append((business_type, str(pk)))
    return refs


def _business_ids_for_member(member_id: int) -> list[str]:
    return [business_id for _, business_id in _business_refs_for_member(member_id)]


def user_attachments_queryset(*, user_id: int):
    """用户上传的全部附件；成员页不做成员维度筛选，各成员下展示该用户全部附件。"""
    return (
        ManagedFile.objects.filter(is_deleted=False, user_id=user_id)
        .prefetch_related("business_relations")
        .order_by("-created_at")
    )


def member_attachments_queryset(*, user_id: int, member_id: int | None = None):
    """兼容旧调用名；member_id 不参与附件筛选。"""
    return user_attachments_queryset(user_id=user_id)


def compute_user_medical_stats(user_id: int) -> dict:
    member_ids = _member_ids_for_user(user_id)
    if not member_ids:
        return {
            "member_count": 0,
            "members_with_data_count": 0,
            "medical_data_total": 0,
            "attachment_count": 0,
            "ai_task_count": 0,
            "last_updated_at": None,
            "last_source": "",
        }

    members_with_data = 0
    total = 0
    ai_task_count = 0
    last_updated_at = None
    last_source = ""

    for member_id in member_ids:
        stats = compute_member_stats(member_id)
        if stats["has_data"]:
            members_with_data += 1
        total += stats["total_count"]

        ai_task_count += HealthExamReport.objects.filter(
            member_id=member_id, is_deleted=False, source=HealthExamReport.Source.OCR
        ).count()
        ai_task_count += ExaminationReport.objects.filter(
            member_id=member_id, is_deleted=False, source=ExaminationReport.Source.OCR
        ).count()

        if stats["last_updated_at"] and (last_updated_at is None or stats["last_updated_at"] > last_updated_at):
            last_updated_at = stats["last_updated_at"]

    ocr_exists = ai_task_count > 0
    if ocr_exists:
        last_source = "AI 识别"

    attachment_count = user_attachments_queryset(user_id=user_id).count()

    return {
        "member_count": len(member_ids),
        "members_with_data_count": members_with_data,
        "medical_data_total": total,
        "attachment_count": attachment_count,
        "ai_task_count": ai_task_count,
        "last_updated_at": last_updated_at,
        "last_source": last_source,
    }


def compute_quality_flags(member_id: int) -> list[dict]:
    flags: list[dict] = []
    today = timezone.localdate()

    for report in HealthExamReport.objects.filter(member_id=member_id, is_deleted=False):
        detail_count = MedExamDetail.objects.filter(
            business_type=MedExamDetail.BusinessType.HEALTH_EXAM_REPORT,
            business_id=report.id,
            is_deleted=False,
        ).count()
        if detail_count == 0:
            flags.append(
                {
                    "type": "details_not_loaded",
                    "resource_type": "health_exam_report",
                    "resource_id": report.id,
                    "message": "体检报告明细未加载",
                }
            )
        if report.source == HealthExamReport.Source.OCR and report.status == HealthExamReport.Status.DRAFT:
            flags.append(
                {
                    "type": "recognition_incomplete",
                    "resource_type": "health_exam_report",
                    "resource_id": report.id,
                    "message": "AI 识别结果未完成",
                }
            )

    for report in ExaminationReport.objects.filter(member_id=member_id, is_deleted=False):
        if report.source == ExaminationReport.Source.OCR and report.status == ExaminationReport.Status.DRAFT:
            flags.append(
                {
                    "type": "recognition_incomplete",
                    "resource_type": "examination_report",
                    "resource_id": report.id,
                    "message": "检查报告 AI 识别未完成",
                }
            )

    for box in MedicineBox.objects.filter(member_id=member_id, is_deleted=False):
        if box.expire_date and box.expire_date < today:
            flags.append(
                {
                    "type": "medicine_expired",
                    "resource_type": "medicine_box",
                    "resource_id": box.id,
                    "message": "药品已过期",
                }
            )
        if box.total_quantity is not None and box.total_quantity < 0:
            flags.append(
                {
                    "type": "negative_stock",
                    "resource_type": "medicine_box",
                    "resource_id": box.id,
                    "message": "库存异常",
                }
            )

    for plan in MedicationPlan.objects.filter(member_id=member_id, is_deleted=False):
        if plan.medicine_box_id is None:
            flags.append(
                {
                    "type": "plan_without_medicine",
                    "resource_type": "medication_plan",
                    "resource_id": plan.id,
                    "message": "用药计划未关联药盒",
                }
            )

    for case in MedicalCase.objects.filter(member_id=member_id, is_deleted=False):
        has_related = (
            Visit.objects.filter(medical_case_id=case.id, is_deleted=False).exists()
            or ExaminationReport.objects.filter(medical_record_id=case.id, is_deleted=False).exists()
            or Prescription.objects.filter(medical_case_id=case.id, is_deleted=False).exists()
        )
        if not has_related:
            flags.append(
                {
                    "type": "orphan_case",
                    "resource_type": "medical_case",
                    "resource_id": case.id,
                    "message": "病例未关联就诊/报告/处方",
                }
            )

    return flags


def admin_files_for_business(business_type: str, business_id: int | str, *, user_id: int | None = None):
    queryset = ManagedFile.objects.filter(
        is_deleted=False,
        business_relations__business_type=business_type,
        business_relations__business_id=str(business_id),
    )
    if user_id is not None:
        queryset = queryset.filter(
            user_id=user_id,
            business_relations__user_id=user_id,
        )
    return queryset.distinct().order_by("-created_at")


def serialize_attachments(business_type: str, business_id: int, *, admin_user, include_url: bool, user_id: int | None = None) -> list[dict]:
    files = admin_files_for_business(business_type, business_id, user_id=user_id)
    rows = ManagedFileAttachmentOutSerializer(
        files,
        many=True,
        context={"business_type": business_type, "business_id": str(business_id)},
    ).data
    if include_url and admin_can_view_attachment(admin_user):
        return rows
    for row in rows:
        row.pop("file_url", None)
        row.pop("object_key", None)
    return rows


def serialize_member_brief(
    member: Member,
    binding: UserMemberBinding,
    *,
    admin_user,
    stats_payload: dict | None = None,
) -> dict:
    reveal = admin_can_view_sensitive(admin_user)
    stats = stats_payload or compute_member_stats(member.id)
    age = None
    if member.birth_date:
        today = timezone.localdate()
        age = today.year - member.birth_date.year - (
            (today.month, today.day) < (member.birth_date.month, member.birth_date.day)
        )
    shared_count = UserMemberBinding.objects.filter(
        member_id=member.id,
        status=UserMemberBinding.Status.ACTIVE,
    ).count()
    return {
        "member_id": member.id,
        "binding_id": binding.id,
        "name": mask_name(member.name, reveal=reveal),
        "raw_name": member.name if reveal else "",
        "relationship": binding.relationship,
        "relationship_label": format_relationship(binding.relationship),
        "gender": member.gender,
        "gender_label": format_gender(member.gender),
        "birth_date": member.birth_date.isoformat() if member.birth_date and reveal else "",
        "age": age,
        "is_primary": member.is_primary,
        "binding_role": binding.role,
        "binding_role_label": ROLE_LABELS.get(binding.role, binding.role),
        "binding_status": binding.status,
        "can_edit": binding.role in {UserMemberBinding.Role.OWNER, UserMemberBinding.Role.ADMIN, UserMemberBinding.Role.EDITOR},
        "shared_user_count": shared_count,
        "share_summary": "本人创建" if binding.role == UserMemberBinding.Role.OWNER else "被共享",
        **stats,
    }


def serialize_shared_relations(member_id: int, *, admin_user) -> list[dict]:
    reveal = admin_can_view_sensitive(admin_user)
    rows = []
    for binding in (
        UserMemberBinding.objects.filter(member_id=member_id)
        .select_related("user", "invited_by")
        .order_by("-status", "-created_at", "-id")
    ):
        user = binding.user
        rows.append(
            {
                "binding_id": binding.id,
                "user_id": user.id,
                "username": mask_name(format_user_display_name(user), reveal=reveal),
                "email": mask_email(user.email, reveal=reveal),
                "relationship": binding.relationship,
                "relationship_label": format_relationship(binding.relationship),
                "role": binding.role,
                "role_label": ROLE_LABELS.get(binding.role, binding.role),
                "is_owner": binding.role == UserMemberBinding.Role.OWNER,
                "share_source": "邀请" if binding.invited_by_id else "家庭绑定",
                "status": binding.status,
                "status_label": STATUS_LABELS.get(binding.status, binding.status),
                "created_at": binding.created_at,
                "updated_at": binding.updated_at,
            }
        )
    return rows


def serialize_user_medical_row(user, *, admin_user, stats_row=None) -> dict:
    reveal = admin_can_view_sensitive(admin_user)
    if stats_row is not None:
        from backoffice.medical_data_stats_service import user_stats_dict

        stats = user_stats_dict(stats_row)
    else:
        stats = compute_user_medical_stats(user.id)
    return {
        "user_id": user.id,
        "username": mask_name(format_user_display_name(user), reveal=reveal),
        "raw_username": user.username if reveal else "",
        "email": mask_email(user.email, reveal=reveal),
        "phone": "",
        "is_active": user.is_active,
        "user_status": format_user_status(user),
        "is_anonymized": is_anonymized_user(user),
        "date_joined": user.date_joined,
        "last_login": user.last_login,
        **stats,
        "risk_flags": [],
        "quality_flag_count": stats.get("quality_flag_count", 0),
    }


def serialize_user_summary(user, *, admin_user, stats_row=None) -> dict:
    reveal = admin_can_view_sensitive(admin_user)
    if stats_row is not None:
        from backoffice.medical_data_stats_service import user_stats_dict

        stats = user_stats_dict(stats_row)
    else:
        stats = compute_user_medical_stats(user.id)
    return {
        "user_id": user.id,
        "username": mask_name(format_user_display_name(user), reveal=reveal),
        "email": mask_email(user.email, reveal=reveal),
        "is_active": user.is_active,
        "user_status": format_user_status(user),
        "date_joined": user.date_joined,
        "last_login": user.last_login,
        **stats,
    }


def build_timeline_events(member_id: int, *, limit: int = 30) -> list[dict]:
    events: list[dict] = []
    for case in MedicalCase.objects.filter(member_id=member_id, is_deleted=False).order_by("-updated_at")[:20]:
        events.append(
            {
                "date": case.updated_at,
                "type": "medical_case",
                "resource_id": case.id,
                "title": case.title or case.diagnosis_summary or "病例",
            }
        )
    for report in HealthExamReport.objects.filter(member_id=member_id, is_deleted=False).order_by("-exam_date", "-updated_at")[:20]:
        events.append(
            {
                "date": report.exam_date or report.updated_at.date() if hasattr(report.updated_at, "date") else report.updated_at,
                "type": "health_exam_report",
                "resource_id": report.id,
                "title": report.institution_name or "体检报告",
            }
        )
    for report in ExaminationReport.objects.filter(member_id=member_id, is_deleted=False).order_by("-performed_at", "-updated_at")[:20]:
        events.append(
            {
                "date": report.performed_at or report.updated_at,
                "type": "examination_report",
                "resource_id": report.id,
                "title": report.item_name or "检查报告",
            }
        )
    for plan in MedicationPlan.objects.filter(member_id=member_id, is_deleted=False).order_by("-start_date", "-updated_at")[:20]:
        events.append(
            {
                "date": plan.start_date,
                "type": "medication_plan",
                "resource_id": plan.id,
                "title": plan.drug_name or "用药计划",
            }
        )
    for visit in Visit.objects.filter(member_id=member_id, is_deleted=False).order_by("-visited_at", "-updated_at")[:20]:
        events.append(
            {
                "date": visit.visited_at or visit.updated_at,
                "type": "visit",
                "resource_id": visit.id,
                "title": visit.department or "就诊记录",
            }
        )

    def sort_key(item):
        value = item.get("date")
        if isinstance(value, date) and not isinstance(value, datetime):
            return timezone.make_aware(datetime.combine(value, datetime.min.time()))
        if value is None:
            return timezone.make_aware(datetime.min.replace(tzinfo=None), timezone.get_current_timezone())
        if timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_current_timezone())
        return value

    events.sort(key=sort_key, reverse=True)
    return events[:limit]


def _serialize_attachment_list_item(obj: ManagedFile, *, admin_user) -> dict:
    relation = obj.business_relations.order_by("-created_at", "-id").first()
    return {
        "id": obj.id,
        "file_uuid": str(obj.file_uuid),
        "original_name": obj.original_name,
        "mime_type": obj.mime_type,
        "file_size": obj.file_size,
        "business_type": relation.business_type if relation else "",
        "business_id": relation.business_id if relation else "",
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
        "recognition_status": "未知",
    }


def serialize_list_item(resource_type: str, obj, *, admin_user) -> dict:
    reveal = admin_can_view_sensitive(admin_user)

    if resource_type == "attachments" or isinstance(obj, ManagedFile):
        return _serialize_attachment_list_item(obj, admin_user=admin_user)

    business_type, _, _, _ = RESOURCE_TYPE_MAP[resource_type]

    if isinstance(obj, MedicalCase):
        symptom_count = Symptom.objects.filter(medical_case_id=obj.id, is_deleted=False).count()
        visit_count = Visit.objects.filter(medical_case_id=obj.id, is_deleted=False).count()
        exam_count = ExaminationReport.objects.filter(medical_record_id=obj.id, is_deleted=False).count()
        prescription_count = Prescription.objects.filter(medical_case_id=obj.id, is_deleted=False).count()
        attachments = admin_files_for_business(business_type, obj.id, user_id=obj.user_id).count()
        return {
            "id": obj.id,
            "title": mask_text(obj.title or obj.diagnosis_summary, reveal=reveal),
            "diagnosis": mask_text(obj.diagnosis_summary, reveal=reveal),
            "severity": obj.severity or "",
            "hospital_name": obj.hospital_name,
            "occurred_at": obj.created_at,
            "symptom_count": symptom_count,
            "visit_count": visit_count,
            "examination_count": exam_count,
            "prescription_count": prescription_count,
            "source": "手动录入",
            "attachment_count": attachments,
            "updated_at": obj.updated_at,
        }

    if isinstance(obj, HealthExamReport):
        detail_count = MedExamDetail.objects.filter(
            business_type=MedExamDetail.BusinessType.HEALTH_EXAM_REPORT,
            business_id=obj.id,
            is_deleted=False,
        ).count()
        attachments = admin_files_for_business(business_type, obj.id, user_id=obj.user_id).count()
        return {
            "id": obj.id,
            "title": mask_text(obj.institution_name or "体检报告", reveal=reveal),
            "institution_name": obj.institution_name,
            "exam_date": obj.exam_date,
            "summary": mask_text(obj.summary or "", reveal=reveal),
            "detail_count": detail_count,
            "attachment_count": attachments,
            "ai_status": format_source(obj.source),
            "recognition_status": "成功" if obj.status != HealthExamReport.Status.DRAFT else "待处理",
            "source": format_source(obj.source),
            "updated_at": obj.updated_at,
        }

    if isinstance(obj, ExaminationReport):
        detail_count = MedExamDetail.objects.filter(
            business_type=MedExamDetail.BusinessType.EXAMINATION_REPORT,
            business_id=obj.id,
            is_deleted=False,
        ).count()
        abnormal_count = MedExamDetail.objects.filter(
            business_type=MedExamDetail.BusinessType.EXAMINATION_REPORT,
            business_id=obj.id,
            is_deleted=False,
        ).exclude(flag="").count()
        attachments = admin_files_for_business(business_type, obj.id, user_id=obj.user_id).count()
        return {
            "id": obj.id,
            "category": obj.category,
            "sub_category": obj.sub_category,
            "title": mask_text(obj.item_name, reveal=reveal),
            "performed_at": obj.performed_at,
            "organization_name": obj.organization_name,
            "department_name": obj.department_name,
            "findings": mask_text(obj.findings or "", reveal=reveal),
            "impression": mask_text(obj.impression or "", reveal=reveal),
            "abnormal_count": abnormal_count,
            "detail_count": detail_count,
            "attachment_count": attachments,
            "source": format_source(obj.source),
            "updated_at": obj.updated_at,
        }

    if isinstance(obj, MedicineBox):
        expired = bool(obj.expire_date and obj.expire_date < timezone.localdate())
        expiring = bool(
            obj.expire_date
            and not expired
            and obj.expire_date <= timezone.localdate() + timedelta(days=30)
        )
        return {
            "id": obj.id,
            "medicine_name": mask_text(obj.medicine_name, reveal=reveal),
            "strength": obj.strength,
            "dosage_form": obj.dosage_form,
            "total_quantity": str(obj.total_quantity) if obj.total_quantity is not None else "",
            "expire_date": obj.expire_date,
            "expired": expired,
            "expiring_soon": expiring,
            "scope": "家庭共享" if obj.member_id is None else "当前成员",
            "source": "手动录入",
            "updated_at": obj.updated_at,
        }

    if isinstance(obj, Prescription):
        plan_count = MedicationPlan.objects.filter(prescription_id=obj.id, is_deleted=False).count()
        return {
            "id": obj.id,
            "institution_name": obj.institution_name,
            "prescriber_name": obj.prescriber_name,
            "prescription_no": obj.prescription_no or "",
            "diagnosis": mask_text(obj.diagnosis, reveal=reveal),
            "prescribed_at": obj.prescribed_at,
            "status": obj.status,
            "plan_count": plan_count,
            "updated_at": obj.updated_at,
        }

    if isinstance(obj, MedicationPlan):
        return {
            "id": obj.id,
            "drug_name": mask_text(obj.drug_name, reveal=reveal),
            "dose_per_time": obj.dose_per_time,
            "frequency_text": obj.frequency_text,
            "start_date": obj.start_date,
            "end_date": obj.end_date,
            "reminder_times": obj.reminder_times,
            "status": obj.status,
            "updated_at": obj.updated_at,
        }

    if isinstance(obj, MedicationRecord):
        return {
            "id": obj.id,
            "plan_id": obj.plan_id,
            "scheduled_at": obj.scheduled_at,
            "taken_at": obj.taken_at,
            "status": obj.status,
            "planned_dose": obj.planned_dose,
            "actual_dose": obj.actual_dose,
            "updated_at": obj.updated_at,
        }

    if isinstance(obj, Symptom):
        return {
            "id": obj.id,
            "name": mask_text(obj.name, reveal=reveal),
            "severity": obj.severity,
            "started_at": obj.started_at,
            "body_part": obj.body_part,
            "updated_at": obj.updated_at,
        }

    if isinstance(obj, Visit):
        return {
            "id": obj.id,
            "visit_type": obj.visit_type,
            "visited_at": obj.visited_at,
            "department": obj.department,
            "doctor_name": obj.doctor_name,
            "updated_at": obj.updated_at,
        }

    if isinstance(obj, Surgery):
        return {
            "id": obj.id,
            "procedure_name": mask_text(obj.procedure_name, reveal=reveal),
            "performed_at": obj.performed_at,
            "surgeon": obj.surgeon,
            "updated_at": obj.updated_at,
        }

    if isinstance(obj, FollowUp):
        return {
            "id": obj.id,
            "status": obj.status,
            "method": obj.method,
            "planned_at": obj.planned_at,
            "completed_at": obj.completed_at,
            "updated_at": obj.updated_at,
        }

    return {"id": getattr(obj, "id", None), "updated_at": getattr(obj, "updated_at", None)}


def serialize_resource_detail(resource_type: str, obj, *, admin_user) -> dict:
    reveal = admin_can_view_sensitive(admin_user)
    include_raw = admin_can_view_raw_json(admin_user)
    include_attachment_url = admin_can_view_attachment(admin_user)
    business_type, _, serializer_cls, _ = RESOURCE_TYPE_MAP.get(resource_type, (None, None, None, None))

    if resource_type == "attachments":
        relation = obj.business_relations.first()
        bt = relation.business_type if relation else ""
        bid = relation.business_id if relation else ""
        payload = ManagedFileAttachmentOutSerializer(
            obj,
            context={"business_type": bt, "business_id": bid},
        ).data
        if not include_attachment_url:
            payload.pop("file_url", None)
            payload.pop("object_key", None)
        return {
            "resource_type": resource_type,
            "resource_id": obj.id,
            "basic": payload,
            "attachments": [payload],
            "ai_info": {},
            "related": {},
            "audit": {"created_at": obj.created_at, "updated_at": obj.updated_at},
            "raw_json": payload if include_raw else None,
        }

    serializer = serializer_cls(obj)
    basic = dict(serializer.data)
    if not reveal:
        for key in ("diagnosis_summary", "findings", "impression", "summary", "diagnosis", "drug_name", "name", "procedure_name", "title"):
            if key in basic and basic[key]:
                basic[key] = mask_text(str(basic[key]), reveal=False)

    attachments = []
    if business_type:
        attachments = serialize_attachments(
            business_type,
            obj.id,
            admin_user=admin_user,
            include_url=include_attachment_url,
            user_id=getattr(obj, "user_id", None),
        )

    med_exam_details = []
    if isinstance(obj, (HealthExamReport, ExaminationReport)):
        bt = (
            MedExamDetail.BusinessType.HEALTH_EXAM_REPORT
            if isinstance(obj, HealthExamReport)
            else MedExamDetail.BusinessType.EXAMINATION_REPORT
        )
        med_exam_details = list(
            MedExamDetail.objects.filter(business_type=bt, business_id=obj.id, is_deleted=False)
            .order_by("sort_order", "id")
            .values(
                "id",
                "category",
                "sub_category",
                "item_name",
                "item_code",
                "result_value",
                "unit",
                "reference_range",
                "flag",
                "diagnosis",
                "result_at",
            )
        )
        if not reveal:
            for row in med_exam_details:
                if row.get("result_value"):
                    row["result_value"] = mask_text(str(row["result_value"]), reveal=False)

    ai_info: dict[str, Any] = {}
    if isinstance(obj, (HealthExamReport, ExaminationReport)):
        ai_info = {
            "source": format_source(getattr(obj, "source", None)),
            "status": getattr(obj, "status", None),
            "raw_ocr": obj.raw_ocr if include_raw else None,
        }

    related: dict[str, Any] = {}
    if isinstance(obj, MedicalCase):
        related = {
            "symptom_count": Symptom.objects.filter(medical_case_id=obj.id, is_deleted=False).count(),
            "visit_count": Visit.objects.filter(medical_case_id=obj.id, is_deleted=False).count(),
            "prescription_count": Prescription.objects.filter(medical_case_id=obj.id, is_deleted=False).count(),
        }
    if isinstance(obj, Prescription):
        related = {
            "plan_ids": list(
                MedicationPlan.objects.filter(prescription_id=obj.id, is_deleted=False).values_list("id", flat=True)
            )
        }
    if isinstance(obj, MedicationPlan):
        related = {
            "prescription_id": obj.prescription_id,
            "medicine_box_id": obj.medicine_box_id,
            "today_records": list(
                MedicationRecord.objects.filter(plan_id=obj.id, is_deleted=False, scheduled_at__date=timezone.localdate())
                .order_by("scheduled_at")
                .values("id", "status", "scheduled_at", "taken_at", "planned_dose", "actual_dose")
            ),
        }

    return {
        "resource_type": resource_type,
        "resource_id": obj.id,
        "basic": basic,
        "med_exam_details": med_exam_details,
        "attachments": attachments,
        "ai_info": ai_info,
        "related": related,
        "audit": {
            "user_id": getattr(obj, "user_id", None),
            "created_at": getattr(obj, "created_at", None),
            "updated_at": getattr(obj, "updated_at", None),
        },
        "raw_json": basic if include_raw else None,
    }


def global_medical_stats() -> dict:
    users_with_data = (
        User.objects.filter(
            member_bindings__status=UserMemberBinding.Status.ACTIVE,
            member_bindings__member__is_deleted=False,
        )
        .filter(
            Q(member_bindings__member__medical_cases__is_deleted=False)
            | Q(member_bindings__member__health_exam_reports__is_deleted=False)
            | Q(member_bindings__member__examination_reports__is_deleted=False)
            | Q(member_bindings__member__medicine_boxes__is_deleted=False)
            | Q(member_bindings__member__prescriptions__is_deleted=False)
            | Q(member_bindings__member__medication_plans__is_deleted=False)
        )
        .distinct()
        .count()
    )
    ai_users = (
        User.objects.filter(
            Q(member_bindings__member__health_exam_reports__source=HealthExamReport.Source.OCR)
            | Q(member_bindings__member__examination_reports__source=ExaminationReport.Source.OCR)
        )
        .distinct()
        .count()
    )
    total_records = (
        MedicalCase.objects.filter(is_deleted=False).count()
        + HealthExamReport.objects.filter(is_deleted=False).count()
        + ExaminationReport.objects.filter(is_deleted=False).count()
        + MedicineBox.objects.filter(is_deleted=False).count()
        + Prescription.objects.filter(is_deleted=False).count()
        + MedicationPlan.objects.filter(is_deleted=False).count()
        + Symptom.objects.filter(is_deleted=False).count()
        + Visit.objects.filter(is_deleted=False).count()
        + Surgery.objects.filter(is_deleted=False).count()
        + FollowUp.objects.filter(is_deleted=False).count()
    )
    attachment_total = ManagedFile.objects.filter(is_deleted=False).count()
    return {
        "users_with_medical_data": users_with_data,
        "users_with_ai_recognition": ai_users,
        "medical_data_total": total_records,
        "attachment_total": attachment_total,
    }


def attachment_recognition_summary(member_id: int, *, user_id: int) -> dict:
    files = user_attachments_queryset(user_id=user_id)
    ocr_reports = (
        HealthExamReport.objects.filter(member_id=member_id, is_deleted=False, source=HealthExamReport.Source.OCR).count()
        + ExaminationReport.objects.filter(member_id=member_id, is_deleted=False, source=ExaminationReport.Source.OCR).count()
    )
    return {
        "attachment_total": files.count(),
        "ai_recognition_count": ocr_reports,
        "pending": HealthExamReport.objects.filter(
            member_id=member_id, is_deleted=False, source=HealthExamReport.Source.OCR, status=HealthExamReport.Status.DRAFT
        ).count(),
        "completed": ocr_reports,
    }
