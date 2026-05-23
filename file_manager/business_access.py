"""按成员绑定判断业务资源与附件是否对当前用户可见。"""

from __future__ import annotations


def _parse_business_id(business_id) -> int | None:
    if business_id is None:
        return None
    text = str(business_id).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def member_id_for_business(business_type: str, business_id) -> int | None:
    """由 business_type + business_id 解析所属 member_id。"""
    bid = _parse_business_id(business_id)
    if bid is None:
        return None

    from medical.models import (
        ExaminationReport,
        FollowUp,
        HealthExamReport,
        MedicalCase,
        MedicationPlan,
        MedicineBox,
        Prescription,
        Surgery,
        Symptom,
        Visit,
    )

    model_map = {
        "health_exam_report": HealthExamReport,
        "examination_report": ExaminationReport,
        "medical_case": MedicalCase,
        "medicine_box": MedicineBox,
        "prescription_batch": Prescription,
        "medication_plan": MedicationPlan,
        "symptom": Symptom,
        "visit": Visit,
        "surgery": Surgery,
        "follow_up": FollowUp,
    }
    model = model_map.get((business_type or "").strip())
    if model is None:
        return None
    return (
        model.objects.filter(id=bid, is_deleted=False)
        .values_list("member_id", flat=True)
        .first()
    )


def user_can_access_business(user, business_type: str, business_id) -> bool:
    from medical.services import member_binding_service as binding_service

    member_id = member_id_for_business(business_type, business_id)
    if member_id is None:
        return False
    return binding_service.get_active_binding(user=user, member_id=member_id) is not None


def user_can_access_file(user, file_record) -> bool:
    if file_record is None or getattr(file_record, "is_deleted", False):
        return False
    if file_record.user_id == user.id:
        return True
    relations = file_record.business_relations.all()
    if hasattr(file_record, "_prefetched_objects_cache") and "business_relations" in getattr(
        file_record, "_prefetched_objects_cache", {}
    ):
        relations = file_record._prefetched_objects_cache["business_relations"]
    for relation in relations:
        if user_can_access_business(user, relation.business_type, relation.business_id):
            return True
    return False


def filter_accessible_relation_specs(user, relation_specs):
    """仅保留当前用户可访问的业务 ID（用于 ETag fingerprint）。"""
    filtered = []
    for business_type, business_ids in relation_specs:
        allowed = [
            str(item)
            for item in business_ids
            if item is not None and user_can_access_business(user, business_type, item)
        ]
        if allowed:
            filtered.append((business_type, allowed))
    return filtered
