from __future__ import annotations

import hashlib
import re
import uuid
from typing import Iterable

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from chat_sync.ai_models.knowledge import (
    KnowledgeBase,
    KnowledgeBaseKind,
    KnowledgeDocument,
    KnowledgeDocumentScope,
    KnowledgeDocumentSource,
)
from chat_sync.ai_runtime.providers.embedding_gateway import EmbeddingGateway
from chat_sync.ai_runtime.providers.exceptions import LLMAPIError, LLMAuthenticationError, LLMConfigError, LLMTimeoutError

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    Hospital,
    HospitalDepartment,
    HospitalKnowledgeBaseDepartment,
    HospitalKnowledgeBaseProfile,
    HospitalKnowledgeChunk,
)
from hospital_care.services.ai_catalog import resolve_embedding_route_for_binding
from hospital_care.services.audit import write_hospital_audit_log

User = get_user_model()

CHUNK_SIZE = 800
EMBED_BATCH_SIZE = 16
SERVICE_USER_PREFIX = "hospital_kb_svc_"


def _lock_hospital(hospital_id) -> Hospital:
    hospital = Hospital.objects.select_for_update().filter(pk=hospital_id).first()
    if hospital is None:
        raise HospitalCareError("HOSPITAL_NOT_FOUND")
    if hospital.status == Hospital.Status.SUSPENDED:
        raise HospitalCareError("HOSPITAL_INACTIVE")
    return hospital


def _knowledge_base_of(profile: HospitalKnowledgeBaseProfile) -> KnowledgeBase:
    knowledge_base = KnowledgeBase.objects.filter(pk=profile.knowledge_base_id).first()
    if knowledge_base is None:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_NOT_FOUND")
    return knowledge_base


def _lock_profile(profile_id) -> HospitalKnowledgeBaseProfile:
    profile = (
        HospitalKnowledgeBaseProfile.objects.select_for_update()
        .select_related("hospital", "embedding_binding")
        .filter(pk=profile_id, is_deleted=False)
        .first()
    )
    if profile is None:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_NOT_FOUND")
    return profile


def _assert_profile_version(profile: HospitalKnowledgeBaseProfile, version) -> None:
    if version is None:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "version"})
    if int(version) != profile.version:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_VERSION_CONFLICT", details={"version": profile.version})


def _assert_document_revision(document: KnowledgeDocument, revision) -> None:
    if revision is None:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "revision"})
    if int(revision) != document.revision:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_VERSION_CONFLICT", details={"revision": document.revision})


def get_or_create_service_user(hospital: Hospital):
    if hospital.knowledge_service_user_id:
        return hospital.knowledge_service_user
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", hospital.code).strip("_") or "hospital"
    username = f"{SERVICE_USER_PREFIX}{slug}"[:150]
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": f"{username}@hospital-knowledge.invalid",
            "is_active": False,
            "is_staff": False,
        },
    )
    if created or user.has_usable_password():
        user.set_unusable_password()
        user.is_active = False
        user.save(update_fields=["password", "is_active"])
    hospital.knowledge_service_user = user
    hospital.save(update_fields=["knowledge_service_user"])
    return user


def _sync_departments(profile: HospitalKnowledgeBaseProfile, department_ids: Iterable | None):
    ids = [item for item in (department_ids or []) if item]
    departments = list(HospitalDepartment.objects.filter(pk__in=ids, hospital_id=profile.hospital_id))
    found = {str(item.id) for item in departments}
    missing = [str(item) for item in ids if str(item) not in found]
    if missing:
        raise HospitalCareError("DEPARTMENT_NOT_FOUND", details={"department_ids": missing})
    HospitalKnowledgeBaseDepartment.objects.filter(profile=profile).exclude(department_id__in=[item.id for item in departments]).delete()
    existing = set(
        HospitalKnowledgeBaseDepartment.objects.filter(profile=profile).values_list("department_id", flat=True)
    )
    for department in departments:
        if department.id not in existing:
            HospitalKnowledgeBaseDepartment.objects.create(profile=profile, department=department)


def _mark_vector_stale(profile: HospitalKnowledgeBaseProfile):
    if profile.vector_status == HospitalKnowledgeBaseProfile.VectorStatus.CURRENT:
        profile.vector_status = HospitalKnowledgeBaseProfile.VectorStatus.STALE


def _bump_knowledge_revision(profile: HospitalKnowledgeBaseProfile):
    kb = _knowledge_base_of(profile)
    kb.revision = int(kb.revision or 1) + 1
    kb.save(update_fields=["revision", "server_updated_at"])
    _mark_vector_stale(profile)


def _content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _excerpt(text: str, limit: int = 200) -> str:
    value = (text or "").strip()
    return value[:limit]


def split_document_content(content: str) -> list[str]:
    text = (content or "").strip()
    if not text:
        return []
    return [text[index : index + CHUNK_SIZE] for index in range(0, len(text), CHUNK_SIZE)]


def create_knowledge_base(*, request, hospital_id, payload: dict) -> HospitalKnowledgeBaseProfile:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "name"})
    actor = request.user
    with transaction.atomic():
        hospital = _lock_hospital(hospital_id)
        service_user = get_or_create_service_user(hospital)
        knowledge_base = KnowledgeBase.objects.create(
            user=service_user,
            name=name,
            kind=KnowledgeBaseKind.SYSTEM,
            is_default=False,
            default_slot=None,
            revision=1,
        )
        profile = HospitalKnowledgeBaseProfile.objects.create(
            hospital=hospital,
            knowledge_base=knowledge_base,
            name=name,
            description=str(payload.get("description") or ""),
            vector_status=HospitalKnowledgeBaseProfile.VectorStatus.NOT_BUILT,
            created_by=actor,
            updated_by=actor,
        )
        _sync_departments(profile, payload.get("department_ids"))
    write_hospital_audit_log(
        request,
        action="hospital.knowledge.create",
        resource_type="hospital_knowledge",
        resource_id=str(profile.id),
        extra={"hospital_id": str(hospital.id), "profile_id": str(profile.id), "name": profile.name},
    )
    return profile


def update_knowledge_base(*, request, profile_id, payload: dict) -> HospitalKnowledgeBaseProfile:
    with transaction.atomic():
        profile = _lock_profile(profile_id)
        _assert_profile_version(profile, payload.get("version"))
        if "name" in payload and payload["name"] is not None:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise HospitalCareError("PAYLOAD_INVALID", details={"field": "name"})
            profile.name = name
            knowledge_base = _knowledge_base_of(profile)
            knowledge_base.name = name
            knowledge_base.save(update_fields=["name", "server_updated_at"])
        if "description" in payload and payload["description"] is not None:
            profile.description = str(payload.get("description") or "")
        if "department_ids" in payload:
            _sync_departments(profile, payload.get("department_ids"))
        profile.updated_by = request.user
        profile.version += 1
        profile.save()
    write_hospital_audit_log(
        request,
        action="hospital.knowledge.update",
        resource_type="hospital_knowledge",
        resource_id=str(profile.id),
        extra={
            "hospital_id": str(profile.hospital_id),
            "profile_id": str(profile.id),
            "name": profile.name,
            "version": profile.version,
        },
    )
    return profile


def soft_delete_knowledge_base(*, request, profile_id, version) -> HospitalKnowledgeBaseProfile:
    with transaction.atomic():
        profile = _lock_profile(profile_id)
        _assert_profile_version(profile, version)
        profile.is_deleted = True
        profile.deleted_at = timezone.now()
        profile.updated_by = request.user
        profile.version += 1
        profile.save(update_fields=["is_deleted", "deleted_at", "updated_by", "version", "updated_at"])
    write_hospital_audit_log(
        request,
        action="hospital.knowledge.delete",
        resource_type="hospital_knowledge",
        resource_id=str(profile.id),
        extra={"hospital_id": str(profile.hospital_id), "profile_id": str(profile.id), "version": profile.version},
    )
    return profile


def _get_document(profile: HospitalKnowledgeBaseProfile, document_id) -> KnowledgeDocument:
    document = KnowledgeDocument.objects.filter(
        pk=document_id,
        knowledge_base_id=profile.knowledge_base_id,
        is_deleted=False,
    ).first()
    if document is None:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_DOCUMENT_NOT_FOUND")
    return document


def create_document(*, request, profile_id, payload: dict) -> KnowledgeDocument:
    title = str(payload.get("title") or "").strip()
    content = str(payload.get("content") or "")
    if not title:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "title"})
    with transaction.atomic():
        profile = _lock_profile(profile_id)
        _assert_profile_version(profile, payload.get("version"))
        knowledge_base = _knowledge_base_of(profile)
        service_user = profile.hospital.knowledge_service_user or knowledge_base.user
        document = KnowledgeDocument.objects.create(
            id=uuid.uuid4(),
            user=service_user,
            knowledge_base=knowledge_base,
            title=title,
            content=content,
            excerpt=_excerpt(content),
            scope=KnowledgeDocumentScope.AGENT_BOUND,
            source=KnowledgeDocumentSource.USER,
            revision=1,
            content_hash=_content_hash(content),
        )
        _bump_knowledge_revision(profile)
        profile.updated_by = request.user
        profile.version += 1
        profile.save()
    write_hospital_audit_log(
        request,
        action="hospital.knowledge.document_create",
        resource_type="hospital_knowledge",
        resource_id=str(profile.id),
        extra={
            "hospital_id": str(profile.hospital_id),
            "profile_id": str(profile.id),
            "document_id": str(document.id),
            "name": title,
        },
    )
    return document


def update_document(*, request, profile_id, document_id, payload: dict) -> KnowledgeDocument:
    with transaction.atomic():
        profile = _lock_profile(profile_id)
        document = _get_document(profile, document_id)
        _assert_document_revision(document, payload.get("revision"))
        if "title" in payload and payload["title"] is not None:
            title = str(payload.get("title") or "").strip()
            if not title:
                raise HospitalCareError("PAYLOAD_INVALID", details={"field": "title"})
            document.title = title
        if "content" in payload and payload["content"] is not None:
            document.content = str(payload.get("content") or "")
            document.excerpt = _excerpt(document.content)
            document.content_hash = _content_hash(document.content)
        document.revision += 1
        document.save()
        _bump_knowledge_revision(profile)
        profile.updated_by = request.user
        profile.version += 1
        profile.save()
    write_hospital_audit_log(
        request,
        action="hospital.knowledge.document_update",
        resource_type="hospital_knowledge",
        resource_id=str(profile.id),
        extra={
            "hospital_id": str(profile.hospital_id),
            "profile_id": str(profile.id),
            "document_id": str(document.id),
            "version": profile.version,
        },
    )
    return document


def delete_document(*, request, profile_id, document_id, revision) -> KnowledgeDocument:
    with transaction.atomic():
        profile = _lock_profile(profile_id)
        document = _get_document(profile, document_id)
        _assert_document_revision(document, revision)
        document.is_deleted = True
        document.deleted_at = timezone.now()
        document.revision += 1
        document.save(update_fields=["is_deleted", "deleted_at", "revision", "server_updated_at"])
        _bump_knowledge_revision(profile)
        profile.updated_by = request.user
        profile.version += 1
        profile.save()
    write_hospital_audit_log(
        request,
        action="hospital.knowledge.document_delete",
        resource_type="hospital_knowledge",
        resource_id=str(profile.id),
        extra={
            "hospital_id": str(profile.hospital_id),
            "profile_id": str(profile.id),
            "document_id": str(document.id),
        },
    )
    return document


def _embed_texts(texts: list[str], route) -> list[list[float]]:
    if not texts:
        return []
    gateway = EmbeddingGateway(route)
    vectors: list[list[float]] = []
    try:
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[start : start + EMBED_BATCH_SIZE]
            vectors.extend(gateway.embed(batch))
    except (LLMConfigError, LLMAPIError, LLMAuthenticationError, LLMTimeoutError) as exc:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_EMBEDDING_UNAVAILABLE", details={"reason": str(exc)}) from exc
    if len(vectors) != len(texts):
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_EMBEDDING_UNAVAILABLE", details={"reason": "count_mismatch"})
    return vectors


def build_vectors(*, request, profile_id, embedding_binding_id, version) -> HospitalKnowledgeBaseProfile:
    binding, route = resolve_embedding_route_for_binding(embedding_binding_id)
    profile = HospitalKnowledgeBaseProfile.objects.select_related("hospital").filter(pk=profile_id, is_deleted=False).first()
    if profile is None:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_NOT_FOUND")
    _assert_profile_version(profile, version)
    documents = list(
        KnowledgeDocument.objects.filter(knowledge_base_id=profile.knowledge_base_id, is_deleted=False).order_by("created_at", "id")
    )
    prepared: list[tuple[KnowledgeDocument, int, str]] = []
    texts: list[str] = []
    for document in documents:
        for index, chunk_text in enumerate(split_document_content(document.content)):
            prepared.append((document, index, chunk_text))
            texts.append(chunk_text)
    vectors = _embed_texts(texts, route)
    with transaction.atomic():
        locked = _lock_profile(profile_id)
        _assert_profile_version(locked, version)
        HospitalKnowledgeChunk.objects.filter(profile=locked).delete()
        rows = [
            HospitalKnowledgeChunk(
                profile=locked,
                document_id=document.id,
                document_revision=document.revision,
                chunk_index=index,
                content=chunk_text,
                content_hash=_content_hash(chunk_text),
                embedding_binding=binding,
                vector_payload=vector,
            )
            for (document, index, chunk_text), vector in zip(prepared, vectors)
        ]
        if rows:
            HospitalKnowledgeChunk.objects.bulk_create(rows)
        locked.indexed_revision = _knowledge_base_of(locked).revision
        locked.vector_status = HospitalKnowledgeBaseProfile.VectorStatus.CURRENT
        locked.embedding_binding = binding
        locked.updated_by = request.user
        locked.version += 1
        locked.save()
        profile = locked
    write_hospital_audit_log(
        request,
        action="hospital.knowledge.vector_build",
        resource_type="hospital_knowledge",
        resource_id=str(profile.id),
        extra={
            "hospital_id": str(profile.hospital_id),
            "profile_id": str(profile.id),
            "embedding_binding_id": binding.id,
            "vector_status": profile.vector_status,
            "document_count": len(documents),
            "chunk_count": len(rows),
            "indexed_revision": profile.indexed_revision,
            "version": profile.version,
        },
    )
    return profile
