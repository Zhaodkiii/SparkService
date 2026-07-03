from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Iterable

from django.conf import settings
from django.contrib.auth.models import User
from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from file_manager.models import ManagedFile
from file_manager.serializers import ManagedFileAttachmentOutSerializer
from file_manager.url_utils import managed_file_download_url
from medical.models import (
    ExaminationReport,
    FollowUp,
    HealthExamReport,
    MedicalCase,
    MedicalShareRecord,
    MedicationPlan,
    MedicineBox,
    Member,
    Prescription,
    Surgery,
    Symptom,
    Visit,
)

SHARE_WEB_BASE_URL = (getattr(settings, "MEDICAL_SHARE_WEB_BASE_URL", "") or "").strip() or "https://share.dreamwhale.top"
SHARE_EXPIRES_DAYS = 10
ATTACHMENT_SIGN_MAX_AGE = 60 * 10
ATTACHMENT_SIGNER = signing.TimestampSigner(salt="spark-medical-share-attachment")


class MedicalShareError(Exception):
    pass


def share_web_url(share_code: str) -> str:
    return f"{SHARE_WEB_BASE_URL.rstrip('/')}/s/{share_code}"


def _supported_business_types() -> set[str]:
    return {MedicalShareRecord.BusinessType.MEDICAL_CASE}


def _generate_share_code(length: int = 16) -> str:
    token = secrets.token_urlsafe(length)
    cleaned = "".join(ch for ch in token if ch.isalnum())
    if len(cleaned) >= 12:
        return cleaned[:16]
    fallback = secrets.token_hex(8)
    return fallback[:16]


def _mask_display_name(name: str) -> str:
    trimmed = (name or "").strip()
    if not trimmed:
        return "匿名用户"
    if len(trimmed) == 1:
        return f"{trimmed}*"
    return f"{trimmed[0]}**"


def _age_text(birth_date) -> str:
    if birth_date is None:
        return ""
    today = timezone.localdate()
    years = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    if years < 0:
        years = 0
    return f"{years}岁"


def _status_badge_text(status: int | None) -> str | None:
    if status is None:
        return None
    mapping = {
        0: "待诊断",
        1: "治疗中",
        2: "复诊",
        3: "慢病管理",
        4: "已康复",
    }
    return mapping.get(status)


def _detail_line(parts: Iterable[str]) -> str:
    return " · ".join([part for part in parts if part])


def _attachment_queryset(business_type: str, business_id: int):
    return (
        ManagedFile.objects.filter(
            is_deleted=False,
            business_relations__business_type=business_type,
            business_relations__business_id=str(business_id),
        )
        .distinct()
        .order_by("-created_at", "-id")
    )


def _serialize_attachment(share_code: str, file_obj: ManagedFile) -> dict:
    payload = ManagedFileAttachmentOutSerializer(file_obj).data
    payload["download_url"] = public_attachment_download_url(share_code, file_obj.id)
    return payload


def public_attachment_download_url(share_code: str, attachment_id: int) -> str:
    token = ATTACHMENT_SIGNER.sign(f"{share_code}:{attachment_id}")
    return f"{share_web_url(share_code)}/api/v1/medical/shares/public/{share_code}/attachments/{attachment_id}/?token={token}"


def verify_attachment_token(*, share_code: str, attachment_id: int, token: str) -> None:
    payload = ATTACHMENT_SIGNER.unsign(token, max_age=ATTACHMENT_SIGN_MAX_AGE)
    if payload != f"{share_code}:{attachment_id}":
        raise signing.BadSignature("share_attachment_mismatch")


def create_or_reuse_share_record(
    *,
    user: User,
    member: Member,
    business_type: str,
    business_id: int,
    title: str = "",
) -> tuple[MedicalShareRecord, bool]:
    if business_type not in _supported_business_types():
        raise MedicalShareError("invalid_business_type")

    now = timezone.now()
    active = (
        MedicalShareRecord.objects.filter(
            user=user,
            member=member,
            business_type=business_type,
            business_id=business_id,
            status=MedicalShareRecord.Status.ACTIVE,
            expires_at__gt=now,
        )
        .order_by("-updated_at", "-id")
        .first()
    )
    if active is not None:
        if title and active.title != title:
            active.title = title
            active.save(update_fields=["title", "updated_at"])
        return active, False

    expires_at = now + timedelta(days=SHARE_EXPIRES_DAYS)
    for _ in range(8):
        share_code = _generate_share_code()
        try:
            with transaction.atomic():
                record = MedicalShareRecord.objects.create(
                    user=user,
                    member=member,
                    business_type=business_type,
                    business_id=business_id,
                    share_code=share_code,
                    title=title or "",
                    status=MedicalShareRecord.Status.ACTIVE,
                    expires_at=expires_at,
                )
            return record, True
        except IntegrityError:
            continue
    raise MedicalShareError("share_code_generation_failed")


def revoke_share_record(record: MedicalShareRecord) -> MedicalShareRecord:
    if record.status != MedicalShareRecord.Status.REVOKED:
        record.status = MedicalShareRecord.Status.REVOKED
        record.save(update_fields=["status", "updated_at"])
    return record


def is_share_record_active(record: MedicalShareRecord) -> bool:
    return record.status == MedicalShareRecord.Status.ACTIVE and record.expires_at > timezone.now()


def touch_share_record(record: MedicalShareRecord) -> MedicalShareRecord:
    record.access_count += 1
    record.last_accessed_at = timezone.now()
    record.save(update_fields=["access_count", "last_accessed_at", "updated_at"])
    return record


def get_share_record_or_none(share_code: str) -> MedicalShareRecord | None:
    return MedicalShareRecord.objects.select_related("member").filter(share_code=share_code).first()


def build_public_share_payload(record: MedicalShareRecord) -> dict:
    if record.business_type != MedicalShareRecord.BusinessType.MEDICAL_CASE:
        raise MedicalShareError("unsupported_business_type")

    try:
        case = MedicalCase.objects.select_related("member").get(
            pk=record.business_id,
            member_id=record.member_id,
            is_deleted=False,
        )
    except MedicalCase.DoesNotExist as exc:
        raise MedicalShareError("business_deleted") from exc

    member = case.member
    attachments = _attachment_queryset("medical_case", case.id)
    medical_case_payload = {
        "id": case.id,
        "title": case.title,
        "record_type": case.record_type,
        "status": case.status,
        "status_badge_text": _status_badge_text(case.status),
        "diagnosis_summary": case.diagnosis_summary,
        "hospital_name": case.hospital_name,
        "age_at_visit": case.age_at_visit,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "attachments": [_serialize_attachment(record.share_code, file_obj) for file_obj in attachments],
        "extra": case.extra,
    }

    timeline = _build_case_timeline(record.share_code, case)
    member_payload = {
        "id": member.id,
        "display_name": _mask_display_name(member.name),
        "gender": member.gender,
        "age_text": _age_text(member.birth_date),
    }
    share_payload = {
        "share_code": record.share_code,
        "business_type": record.business_type,
        "business_id": record.business_id,
        "status": record.status,
        "expires_at": record.expires_at,
        "title": record.title or case.title,
        "share_url": share_web_url(record.share_code),
    }
    download_app_payload = {
        "title": "下载 App 查看和管理完整健康档案",
        "description": "当前链接已经进入公开分享页。你可以下载 Spark App 继续查看完整病例、管理成员和上传更多资料。",
        "button_text": "下载 App",
        "url": getattr(settings, "MEDICAL_SHARE_DOWNLOAD_URL", "") or "https://www.dreamhua.top/",
    }
    return {
        "share": share_payload,
        "member": member_payload,
        "case": medical_case_payload,
        "timeline": timeline,
        "download_app": download_app_payload,
    }


def _build_case_timeline(share_code: str, case: MedicalCase) -> list[dict]:
    case_id = case.id
    nested_plan_ids: set[int] = set()
    events: list[dict] = []

    prescriptions = list(
        Prescription.objects.filter(is_deleted=False, medical_case_id=case_id)
        .select_related("member")
        .order_by("-prescribed_at", "-updated_at", "-id")
    )
    medication_plans = list(
        MedicationPlan.objects.filter(is_deleted=False, medical_case_id=case_id)
        .select_related("medicine_box", "prescription")
        .order_by("-start_date", "-updated_at", "-id")
    )
    symptom_rows = list(Symptom.objects.filter(is_deleted=False, medical_case_id=case_id).order_by("-created_at", "-updated_at", "-id"))
    visit_rows = list(Visit.objects.filter(is_deleted=False, medical_case_id=case_id).order_by("-visited_at", "-updated_at", "-id"))
    surgery_rows = list(Surgery.objects.filter(is_deleted=False, medical_case_id=case_id).order_by("-performed_at", "-updated_at", "-id"))
    follow_up_rows = list(FollowUp.objects.filter(is_deleted=False, medical_case_id=case_id).order_by("-completed_at", "-updated_at", "-id"))
    examination_rows = list(
        ExaminationReport.objects.filter(is_deleted=False, medical_record_id=case_id)
        .order_by("-performed_at", "-updated_at", "-id")
    )

    for prescription in prescriptions:
        plans = [plan for plan in medication_plans if plan.prescription_id == prescription.id]
        nested_plan_ids.update(plan.id for plan in plans)
        title = prescription.institution_name or prescription.prescriber_name or prescription.prescription_no or "处方"
        detail = prescription.diagnosis or ""
        events.append(
            {
                "id": f"prescription-{prescription.id}",
                "kind": "prescription",
                "title": title,
                "detail": detail,
                "date": prescription.prescribed_at or prescription.updated_at,
                "status_badge_text": None,
                "attachments": _timeline_attachments("prescription", prescription.id, share_code),
                "nested_medication_plans": [_serialize_medication_plan(plan, share_code) for plan in plans],
                "prescription": _serialize_prescription(prescription, share_code),
            }
        )

    for plan in medication_plans:
        if plan.id in nested_plan_ids:
            continue
        events.append(_serialize_medication_plan_event(plan, share_code))

    for row in examination_rows:
        row_date = row.reported_at or row.performed_at or row.updated_at or row.created_at
        title = row.item_name or row.sub_category or row.category or "检查报告"
        detail = row.impression or row.findings or ""
        events.append(
            {
                "id": f"examination-{row.id}",
                "kind": "examination",
                "category": row.category or "",
                "title": title,
                "detail": detail,
                "date": row_date,
                "status_badge_text": None,
                "attachments": _timeline_attachments("examination_report", row.id, share_code),
                "examination": _serialize_examination_report(row, share_code),
            }
        )

    for row in symptom_rows:
        row_date = row.started_at or row.updated_at
        events.append(
            {
                "id": f"symptom-{row.id}",
                "kind": "symptom",
                "title": row.name,
                "detail": _detail_line([row.severity, row.body_part, row.notes]),
                "date": row_date,
                "status_badge_text": None,
                "attachments": _timeline_attachments("symptom", row.id, share_code),
                "symptom": _serialize_symptom(row, share_code),
            }
        )

    for row in visit_rows:
        row_date = row.visited_at or row.updated_at
        events.append(
            {
                "id": f"visit-{row.id}",
                "kind": "visit",
                "title": row.department or "就诊信息",
                "detail": _detail_line([row.doctor_name, row.visit_no, row.notes]),
                "date": row_date,
                "status_badge_text": None,
                "attachments": _timeline_attachments("visit", row.id, share_code),
                "visit": _serialize_visit(row, share_code),
            }
        )

    for row in surgery_rows:
        row_date = row.performed_at or row.updated_at
        events.append(
            {
                "id": f"surgery-{row.id}",
                "kind": "surgery",
                "title": row.procedure_name,
                "detail": _detail_line([row.surgeon, row.site, row.notes]),
                "date": row_date,
                "status_badge_text": None,
                "attachments": _timeline_attachments("surgery", row.id, share_code),
                "surgery": _serialize_surgery(row, share_code),
            }
        )

    for row in follow_up_rows:
        row_date = row.completed_at or row.planned_at or row.updated_at
        events.append(
            {
                "id": f"follow-up-{row.id}",
                "kind": "follow_up",
                "title": row.method or row.status or "随访",
                "detail": _detail_line([row.outcome, row.next_action]),
                "date": row_date,
                "status_badge_text": None,
                "attachments": _timeline_attachments("follow_up", row.id, share_code),
                "follow_up": _serialize_follow_up(row, share_code),
            }
        )

    meta_detail = []
    if case.hospital_name:
        meta_detail.append(f"医院：{case.hospital_name}")
    if case.record_type:
        meta_detail.append(f"类型：{case.record_type}")
    if case.age_at_visit is not None:
        meta_detail.append(f"年龄：{case.age_at_visit}")
    if meta_detail:
        events.append(
            {
                "id": "meta",
                "kind": "meta",
                "title": "病例信息",
                "detail": "\n".join(meta_detail),
                "date": case.updated_at or case.created_at,
                "status_badge_text": _status_badge_text(case.status),
                "attachments": [],
            }
        )

    events.sort(key=lambda item: item["date"] or timezone.now(), reverse=True)
    return events


def _serialize_prescription(prescription: Prescription, share_code: str) -> dict:
    return {
        "id": prescription.id,
        "title": prescription.institution_name or prescription.prescriber_name or prescription.prescription_no or "处方",
        "diagnosis": prescription.diagnosis,
        "prescribed_at": prescription.prescribed_at,
        "status": prescription.status,
        "attachments": _timeline_attachments("prescription", prescription.id, share_code),
    }


def _serialize_medication_plan(plan: MedicationPlan, share_code: str) -> dict:
    box_name = plan.medicine_box.medicine_name if plan.medicine_box else ""
    return {
        "id": plan.id,
        "drug_name": plan.drug_name,
        "dose_per_time": plan.dose_per_time,
        "frequency_text": plan.frequency_text,
        "start_date": plan.start_date,
        "status": plan.status,
        "box_name": box_name,
        "attachments": _timeline_attachments("medication_plan", plan.id, share_code),
    }


def _serialize_medication_plan_event(plan: MedicationPlan, share_code: str) -> dict:
    title = plan.drug_name or "用药"
    detail = _detail_line([
        plan.dose_per_time,
        plan.frequency_text,
        ", ".join([item.get("time", "") for item in (plan.reminder_times or []) if isinstance(item, dict)]),
        f"存量 {plan.medicine_box.total_quantity}" if getattr(plan, "medicine_box", None) and plan.medicine_box.total_quantity is not None else "",
    ])
    return {
        "id": f"medication-plan-{plan.id}",
        "kind": "medication",
        "title": title,
        "detail": detail,
        "date": plan.start_date or plan.updated_at,
        "status_badge_text": None,
        "attachments": _timeline_attachments("medication_plan", plan.id, share_code),
        "medication_plan": _serialize_medication_plan(plan, share_code),
    }


def _serialize_examination_report(report: ExaminationReport, share_code: str) -> dict:
    return {
        "id": report.id,
        "category": report.category,
        "sub_category": report.sub_category,
        "item_name": report.item_name,
        "findings": report.findings,
        "impression": report.impression,
        "performed_at": report.performed_at,
        "reported_at": report.reported_at,
        "status": report.status,
        "attachments": _timeline_attachments("examination_report", report.id, share_code),
    }


def _serialize_symptom(symptom: Symptom, share_code: str) -> dict:
    return {
        "id": symptom.id,
        "name": symptom.name,
        "severity": symptom.severity,
        "body_part": symptom.body_part,
        "notes": symptom.notes,
        "started_at": symptom.started_at,
        "attachments": _timeline_attachments("symptom", symptom.id, share_code),
    }


def _serialize_visit(visit: Visit, share_code: str) -> dict:
    return {
        "id": visit.id,
        "visit_type": visit.visit_type,
        "visited_at": visit.visited_at,
        "department": visit.department,
        "doctor_name": visit.doctor_name,
        "visit_no": visit.visit_no,
        "notes": visit.notes,
        "attachments": _timeline_attachments("visit", visit.id, share_code),
    }


def _serialize_surgery(surgery: Surgery, share_code: str) -> dict:
    return {
        "id": surgery.id,
        "procedure_name": surgery.procedure_name,
        "site": surgery.site,
        "performed_at": surgery.performed_at,
        "surgeon": surgery.surgeon,
        "notes": surgery.notes,
        "attachments": _timeline_attachments("surgery", surgery.id, share_code),
    }


def _serialize_follow_up(follow_up: FollowUp, share_code: str) -> dict:
    return {
        "id": follow_up.id,
        "planned_at": follow_up.planned_at,
        "completed_at": follow_up.completed_at,
        "status": follow_up.status,
        "method": follow_up.method,
        "outcome": follow_up.outcome,
        "next_action": follow_up.next_action,
        "attachments": _timeline_attachments("follow_up", follow_up.id, share_code),
    }


def _timeline_attachments(business_type: str, business_id: int, share_code: str) -> list[dict]:
    queryset = _attachment_queryset(business_type, business_id)
    return [_serialize_attachment(share_code, item) for item in queryset]
