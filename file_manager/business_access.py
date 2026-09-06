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
    # DOCTOR-WORKSPACE-000004：问诊附件 business_id 为 thread UUID，直接取 Thread 所属 member。
    if (business_type or "").strip() == "hospital_conversation":
        from chat_sync.models import ChatThread

        return (
            ChatThread.objects.filter(id=str(business_id or "").strip(), is_deleted=False)
            .values_list("member_id", flat=True)
            .first()
        )
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
    from nutrition.models import NutritionAppleHealthIntakeImport, NutritionEnergyBurnRecord, NutritionMealRecord

    nutrition_model_map = {
        "nutrition_meal_record": NutritionMealRecord,
        "nutrition_apple_health_intake_import": NutritionAppleHealthIntakeImport,
        "nutrition_energy_burn_record": NutritionEnergyBurnRecord,
    }
    model = model_map.get((business_type or "").strip()) or nutrition_model_map.get((business_type or "").strip())
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


def _doctor_can_preview_hospital_file(user, file_record) -> bool:
    """医生工作台：可预览其负责问诊消息块中的附件（含患者 SparkClient 上传）。"""
    from chat_sync.models import ChatMessageBlock
    from hospital_care.models import ClinicalConversationBinding, DoctorProfile

    doctor = DoctorProfile.objects.select_related("staff_membership").filter(staff_membership__user=user).first()
    if doctor is None:
        return False

    doctor_thread_ids = {
        str(thread_id)
        for thread_id in ClinicalConversationBinding.objects.filter(
            doctor=doctor,
            hospital_id=doctor.staff_membership.hospital_id,
            thread__is_deleted=False,
        ).values_list("thread_id", flat=True)
    }
    if not doctor_thread_ids:
        return False

    relation_thread_ids = {
        str(relation.business_id)
        for relation in file_record.business_relations.all()
        if relation.business_type == "hospital_conversation"
    }
    if relation_thread_ids.intersection(doctor_thread_ids):
        return True

    target_file_id = file_record.id
    blocks = ChatMessageBlock.objects.filter(
        thread_id__in=doctor_thread_ids,
        kind__in=["imageGallery", "fileGallery", "fileAttachments"],
        message__tombstone=False,
    ).only("payload")
    for block in blocks.iterator(chunk_size=100):
        payload = block.payload or {}
        for key in ("image_gallery", "file_gallery", "file_attachments"):
            gallery = payload.get(key)
            if not isinstance(gallery, dict):
                continue
            for value in gallery.values():
                if not isinstance(value, list):
                    continue
                for entry in value:
                    if isinstance(entry, dict) and entry.get("file_id") == target_file_id:
                        return True
    return False


def user_can_preview_file(user, file_record) -> bool:
    if user_can_access_file(user, file_record):
        return True
    return _doctor_can_preview_hospital_file(user, file_record)


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
