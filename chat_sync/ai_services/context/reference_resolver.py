from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Q


class ReferenceResolutionError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ResolvedSource:
    source_id: str
    source_type: str
    title: str
    content: str
    version: str
    content_hash: str
    metadata: dict[str, Any]


def resolve_references(*, user, thread, references: list[dict[str, Any]], attachments: list[dict[str, Any]]) -> tuple[ResolvedSource, ...]:
    sources: list[ResolvedSource] = []
    member_id = thread.member_id
    if member_id is not None:
        sources.append(_resolve_member(user, member_id))
    for reference in references:
        kind = str(reference.get("type") or "")
        if kind == "health_resource":
            sources.append(_resolve_health(user, member_id, reference))
        else:
            raise ReferenceResolutionError("chat_context_reference_invalid", "unsupported reference type")
    for attachment in attachments:
        sources.append(_resolve_file(user, attachment))
    return tuple(sources)


def _resolve_member(user, member_id: int) -> ResolvedSource:
    from medical.models import Member, MemberMedicalProfile
    from medical.services.member_binding_service import get_active_binding

    if get_active_binding(user=user, member_id=member_id) is None:
        raise ReferenceResolutionError("chat_context_access_revoked", "member access revoked")
    member = Member.objects.filter(id=member_id, is_deleted=False).first()
    if member is None:
        raise ReferenceResolutionError("chat_context_resource_not_found", "member not found")
    profile = MemberMedicalProfile.objects.filter(member_id=member_id, user=user, is_deleted=False).first()
    fields = [f"name: {member.name[:64]}", f"gender: {member.gender}"]
    if member.birth_date:
        fields.append(f"birth_date: {member.birth_date.isoformat()}")
    if member.blood_type:
        fields.append(f"blood_type: {member.blood_type}")
    if member.allergies:
        fields.append(f"allergies: {str(member.allergies)[:800]}")
    if profile and profile.chronic_conditions:
        fields.append(f"chronic_conditions: {str(profile.chronic_conditions)[:800]}")
    content = f'<source id="member:{member_id}" trust="untrusted_reference">\n' + "\n".join(fields) + "\n</source>"
    return _source(f"member:{member_id}", "member", member.name, content, str(member.updated_at), {"member_id": member_id})


def _resolve_health(user, member_id: int | None, ref: dict[str, Any]) -> ResolvedSource:
    if member_id is None:
        raise ReferenceResolutionError("chat_context_resource_not_found", "thread has no member")
    from medical.services.member_binding_service import get_active_binding

    if get_active_binding(user=user, member_id=member_id) is None:
        raise ReferenceResolutionError("chat_context_access_revoked", "member access revoked")
    resource_type = str(ref.get("resource_type") or "")
    resource_id = ref.get("resource_id")
    model_map = {
        "medical_case": "MedicalCase",
        "health_exam_report": "HealthExamReport",
        "examination_report": "ExaminationReport",
        "medication_plan": "MedicationPlan",
        "member_key_indicator": "MemberMedicalKeyIndicatorRecord",
    }
    model_name = model_map.get(resource_type)
    if not model_name or not str(resource_id).isdigit():
        raise ReferenceResolutionError("chat_context_reference_invalid", "invalid health resource")
    from medical import models as medical_models

    model = getattr(medical_models, model_name)
    obj = model.objects.filter(Q(id=int(resource_id)), member_id=member_id, is_deleted=False).first()
    if obj is None:
        raise ReferenceResolutionError("chat_context_resource_not_found", "health resource not found")
    fields = []
    for field in ("title", "name", "summary", "diagnosis_summary", "findings", "impression", "drug_name", "frequency_text", "status"):
        value = getattr(obj, field, None)
        if value not in (None, ""):
            fields.append(f"{field}: {str(value)[:1200]}")
    content = f'<source id="{resource_type}:{obj.pk}" trust="untrusted_reference">\n' + "\n".join(fields) + "\n</source>"
    return _source(f"{resource_type}:{obj.pk}", resource_type, resource_type, content, str(getattr(obj, "updated_at", "")), {"member_id": member_id})


def _resolve_file(user, ref: dict[str, Any]) -> ResolvedSource:
    from file_manager.business_access import user_can_access_file
    from file_manager.models import ManagedFile

    file_id = ref.get("file_id")
    query = ManagedFile.objects.prefetch_related("business_relations").filter(is_deleted=False)
    if str(file_id).isdigit():
        query = query.filter(id=int(file_id))
    else:
        try:
            import uuid

            query = query.filter(file_uuid=uuid.UUID(str(file_id)))
        except (TypeError, ValueError, AttributeError):
            raise ReferenceResolutionError("chat_context_reference_invalid", "invalid attachment id")
    obj = query.first()
    if obj is None or not user_can_access_file(user, obj):
        raise ReferenceResolutionError("chat_context_resource_not_found", "attachment not found")
    content = (
        f'<source id="file:{obj.id}" trust="untrusted_reference">\n'
        f"filename: {obj.original_name}\nmime_type: {obj.mime_type}\nfile_size: {obj.file_size}\n"
        "content_status: unavailable (file text extraction is not configured)\n</source>"
    )
    return _source(f"file:{obj.id}", "file", obj.original_name, content, str(obj.updated_at), {"content_status": "unavailable", "file_id": obj.id})


def _source(source_id: str, source_type: str, title: str, content: str, version: str, metadata: dict[str, Any]) -> ResolvedSource:
    import hashlib

    return ResolvedSource(source_id, source_type, title, content, version, hashlib.sha256(content.encode()).hexdigest(), metadata)
