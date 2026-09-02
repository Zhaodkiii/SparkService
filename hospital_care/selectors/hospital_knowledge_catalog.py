from __future__ import annotations

from django.db.models import Count, Q, QuerySet

from ai_config.models import SparkToolName
from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeDocument
from chat_sync.ai_runtime.tools.server_names import SparkServerToolName

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    ClinicalAgentKnowledgeBinding,
    ClinicalAgentProfile,
    DoctorProfile,
    HospitalDepartment,
    HospitalKnowledgeBaseProfile,
    HospitalStaffMembership,
)
from hospital_care.services.ai_catalog import chat_models_for_form, embedding_bindings_for_form


def hospital_knowledge_bases(hospital_id, *, q: str = "", department_id=None) -> QuerySet[HospitalKnowledgeBaseProfile]:
    qs = (
        HospitalKnowledgeBaseProfile.objects.filter(hospital_id=hospital_id, is_deleted=False)
        .select_related("embedding_binding", "embedding_binding__model")
        .prefetch_related("department_links__department")
    )
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if department_id:
        qs = qs.filter(department_links__department_id=department_id)
    return qs.order_by("-updated_at").distinct()


def get_knowledge_base(profile_id) -> HospitalKnowledgeBaseProfile:
    profile = (
        HospitalKnowledgeBaseProfile.objects.select_related("hospital", "embedding_binding", "embedding_binding__model")
        .prefetch_related("department_links__department")
        .filter(pk=profile_id, is_deleted=False)
        .first()
    )
    if profile is None:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_NOT_FOUND")
    _attach_knowledge_stats([profile])
    return profile


def knowledge_base_options_for_agent_form(hospital_id) -> QuerySet[HospitalKnowledgeBaseProfile]:
    return HospitalKnowledgeBaseProfile.objects.filter(hospital_id=hospital_id, is_deleted=False).order_by("name")


def knowledge_documents(profile: HospitalKnowledgeBaseProfile) -> QuerySet[KnowledgeDocument]:
    return KnowledgeDocument.objects.filter(knowledge_base_id=profile.knowledge_base_id, is_deleted=False).order_by(
        "-server_updated_at",
        "id",
    )


def _attach_knowledge_stats(profiles: list[HospitalKnowledgeBaseProfile]) -> None:
    if not profiles:
        return
    kb_ids = [item.knowledge_base_id for item in profiles]
    revisions = {
        str(key).replace("-", "").lower(): value
        for key, value in KnowledgeBase.objects.filter(pk__in=kb_ids).values_list("id", "revision")
    }
    counts = {
        str(item["knowledge_base_id"]).replace("-", "").lower(): item["c"]
        for item in KnowledgeDocument.objects.filter(knowledge_base_id__in=kb_ids, is_deleted=False)
        .values("knowledge_base_id")
        .annotate(c=Count("id"))
    }
    for profile in profiles:
        key = str(profile.knowledge_base_id).replace("-", "").lower()
        profile.revision = revisions.get(key)
        profile.document_count = counts.get(key, 0)


def attach_knowledge_list_stats(profiles: list[HospitalKnowledgeBaseProfile]) -> list[HospitalKnowledgeBaseProfile]:
    _attach_knowledge_stats(profiles)
    return profiles


def knowledge_agent_count(profile: HospitalKnowledgeBaseProfile) -> int:
    return ClinicalAgentKnowledgeBinding.objects.filter(
        knowledge_base_id=profile.knowledge_base_id,
        status=ClinicalAgentKnowledgeBinding.Status.ACTIVE,
    ).count()


def get_agent(agent_id) -> ClinicalAgentProfile:
    agent = (
        ClinicalAgentProfile.objects.select_related(
            "hospital",
            "doctor",
            "department",
            "scenario_binding",
            "scenario_binding__model",
        )
        .prefetch_related("knowledge_bindings")
        .filter(pk=agent_id)
        .first()
    )
    if agent is None:
        raise HospitalCareError("AGENT_NOT_FOUND")
    return agent


def agent_form_options(hospital_id) -> dict:
    doctors = (
        DoctorProfile.objects.select_related("staff_membership")
        .filter(
            staff_membership__hospital_id=hospital_id,
            staff_membership__status=HospitalStaffMembership.Status.ACTIVE,
            staff_membership__role=HospitalStaffMembership.Role.DOCTOR,
            profile_status=DoctorProfile.ProfileStatus.ACTIVE,
        )
        .order_by("display_name")
    )
    departments = HospitalDepartment.objects.filter(
        hospital_id=hospital_id,
        status=HospitalDepartment.Status.ACTIVE,
    ).order_by("sort_order", "name")
    models = chat_models_for_form()
    knowledge_bases = knowledge_base_options_for_agent_form(hospital_id)
    embedding_bindings = embedding_bindings_for_form()
    return {
        "doctors": doctors,
        "departments": departments,
        "models": models,
        "knowledge_bases": knowledge_bases,
        "embedding_bindings": embedding_bindings,
        "ai_tool_scenarios": [{"value": item.value, "label": item.label} for item in SparkToolName],
        "server_tool_scenarios": [{"value": item.value, "label": item.label} for item in SparkServerToolName],
    }
