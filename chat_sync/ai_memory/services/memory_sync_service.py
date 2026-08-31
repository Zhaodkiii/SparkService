from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from chat_sync.ai_memory.constants import AGENT_SCOPE_ENABLED, THREAD_SCOPE_SYNC_ENABLED
from chat_sync.ai_memory.services.idempotency_service import IdempotencyConflict, IdempotencyService, compute_request_hash
from chat_sync.ai_memory.services.keys import (
    clamp_content,
    compute_content_hash,
    compute_dedup_key,
    compute_normalized_key,
    compute_scope_key,
    hash_device_id,
    title_from_content,
    validate_layer_document,
    validate_section_key,
)
from chat_sync.ai_memory.services.payloads import memory_to_snapshot
from chat_sync.ai_models.memory import (
    AIMemory,
    MemoryConfirmationStatus,
    MemoryLayer,
    MemoryMutationOperation,
    MemoryScope,
    MemorySensitivity,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from medical.services.member_permission_service import MemberPermissionDenied


class MemorySyncError(Exception):
    code = "memory_payload_invalid"
    status_code = 400

    def __init__(self, *, snapshot: dict[str, Any] | None = None, reason_code: str | None = None):
        self.snapshot = snapshot
        self.reason_code = reason_code or self.code
        super().__init__(self.code)


class MemoryPayloadInvalidError(MemorySyncError):
    code = "memory_payload_invalid"
    status_code = 400


class MemoryNotFoundError(MemorySyncError):
    code = "memory_not_found"
    status_code = 404


class MemoryDeletedError(MemorySyncError):
    code = "memory_tombstoned"
    status_code = 409


class MemoryRevisionConflictError(MemorySyncError):
    code = "memory_revision_conflict"
    status_code = 409


class DuplicateKeyError(MemorySyncError):
    code = "memory_duplicate_key"
    status_code = 409


class MemoryIdConflictError(MemorySyncError):
    code = "memory_duplicate_key"
    status_code = 409


class MemoryScopeForbiddenError(MemorySyncError):
    code = "memory_scope_forbidden"
    status_code = 403


class MutationIdempotencyConflictError(MemorySyncError):
    code = "memory_mutation_reused"
    status_code = 409


class MemoryOperationUnsupportedError(MemorySyncError):
    code = "memory_operation_unsupported"
    status_code = 400


class MemorySyncService:
    @staticmethod
    def apply_mutation(*, user, mutation: dict[str, Any], actor: str = "sync") -> dict[str, Any]:
        mutation_id = mutation["mutation_id"]
        memory_id = mutation["memory_id"]
        operation = mutation["operation"]
        base_revision = mutation.get("base_revision")
        memory_payload = mutation.get("memory")
        request_hash = compute_request_hash(
            operation=operation,
            memory_id=memory_id,
            base_revision=base_revision,
            memory=memory_payload,
        )
        try:
            with transaction.atomic():
                replay = IdempotencyService.check_replay(user=user, mutation_id=mutation_id, request_hash=request_hash)
                if replay is not None:
                    snapshot = dict(replay.result_snapshot or {})
                    return {
                        "status": "replayed",
                        "replayed": True,
                        "memory_id": str(replay.memory_id),
                        "revision": replay.result_revision,
                        "snapshot": snapshot,
                        "resolution": None,
                        "reason_code": None,
                    }

                if operation == MemoryMutationOperation.CREATE:
                    result = MemorySyncService._apply_create(user=user, mutation=mutation, actor=actor)
                elif operation == MemoryMutationOperation.UPDATE:
                    result = MemorySyncService._apply_update(user=user, mutation=mutation, actor=actor)
                elif operation == MemoryMutationOperation.DELETE:
                    result = MemorySyncService._apply_delete(user=user, mutation=mutation, actor=actor)
                elif operation in (MemoryMutationOperation.CONFIRM, MemoryMutationOperation.REJECT):
                    raise MemoryOperationUnsupportedError()
                else:
                    raise MemoryPayloadInvalidError()

                snapshot = result["snapshot"]
                IdempotencyService.record(
                    user=user,
                    mutation_id=mutation_id,
                    memory_id=memory_id,
                    operation=operation,
                    request_hash=request_hash,
                    base_revision=base_revision,
                    result_revision=int(snapshot.get("revision") or 0),
                    result_snapshot=snapshot,
                )
                return result
        except IdempotencyConflict as exc:
            raise MutationIdempotencyConflictError() from exc

    @staticmethod
    def _apply_create(*, user, mutation: dict[str, Any], actor: str) -> dict[str, Any]:
        memory_id = mutation["memory_id"]
        fields = MemorySyncService._validate_writable_fields(
            user=user, payload=mutation.get("memory") or {}, creating=True
        )
        existing = AIMemory.objects.select_for_update().filter(user=user, id=memory_id).first()
        if existing is not None:
            if existing.is_deleted:
                raise MemoryDeletedError(snapshot=memory_to_snapshot(existing), reason_code="tombstoned")
            if existing.content_hash == fields["content_hash"]:
                return _accepted(existing, replayed=True)
            raise MemoryIdConflictError(snapshot=memory_to_snapshot(existing), reason_code="duplicate_memory_key")

        duplicate = (
            AIMemory.objects.select_for_update()
            .filter(user=user, dedup_key=fields["dedup_key"], is_deleted=False)
            .first()
        )
        if duplicate is not None:
            return {
                "status": "conflict",
                "replayed": False,
                "memory_id": str(duplicate.id),
                "revision": duplicate.revision,
                "snapshot": memory_to_snapshot(duplicate),
                "resolution": "server_wins",
                "reason_code": "duplicate_memory_key",
            }

        device_hash = hash_device_id((mutation.get("client") or {}).get("device_id"))
        memory = AIMemory.objects.create(
            id=memory_id,
            user=user,
            revision=1,
            origin_device_id_hash=device_hash,
            last_device_id_hash=device_hash,
            **fields,
        )
        return _accepted(memory, replayed=False)

    @staticmethod
    def _apply_update(*, user, mutation: dict[str, Any], actor: str) -> dict[str, Any]:
        memory = _lock_owned(user, mutation["memory_id"])
        _assert_revision(memory, mutation.get("base_revision"))
        fields = MemorySyncService._validate_writable_fields(
            user=user,
            payload=mutation.get("memory") or {},
            creating=False,
            existing=memory,
        )
        if fields["dedup_key"] != memory.dedup_key:
            conflict = (
                AIMemory.objects.select_for_update()
                .filter(user=user, dedup_key=fields["dedup_key"], is_deleted=False)
                .exclude(id=memory.id)
                .first()
            )
            if conflict is not None:
                raise DuplicateKeyError(snapshot=memory_to_snapshot(conflict), reason_code="duplicate_memory_key")
        for key, value in fields.items():
            setattr(memory, key, value)
        device_hash = hash_device_id((mutation.get("client") or {}).get("device_id"))
        if device_hash:
            memory.last_device_id_hash = device_hash
        memory.revision += 1
        memory.save()
        return _accepted(memory, replayed=False)

    @staticmethod
    def _apply_delete(*, user, mutation: dict[str, Any], actor: str) -> dict[str, Any]:
        memory = _lock_owned(user, mutation["memory_id"], allow_deleted=True)
        if memory.is_deleted:
            return _accepted(memory, replayed=True)
        _assert_revision(memory, mutation.get("base_revision"))
        memory.is_deleted = True
        memory.deleted_at = timezone.now()
        memory.dedup_key = None
        memory.revision += 1
        memory.save()
        return _accepted(memory, replayed=False)

    @staticmethod
    def _validate_writable_fields(
        *,
        user,
        payload: dict[str, Any],
        creating: bool,
        existing: AIMemory | None = None,
    ) -> dict[str, Any]:
        scope = payload.get("scope") or (existing.scope if existing else MemoryScope.ACCOUNT)
        if scope not in MemoryScope.values:
            raise MemoryPayloadInvalidError()
        if scope == MemoryScope.AGENT and not AGENT_SCOPE_ENABLED:
            raise MemoryPayloadInvalidError(reason_code="memory_payload_invalid")
        if scope == MemoryScope.THREAD and not THREAD_SCOPE_SYNC_ENABLED:
            raise MemoryPayloadInvalidError()

        member_id = payload.get("member_id") if "member_id" in payload else (existing.member_id if existing else None)
        agent_key = payload.get("agent_key") if "agent_key" in payload else (existing.agent_key if existing else None)
        thread_id = payload.get("thread_id") if "thread_id" in payload else (existing.thread_id if existing else None)
        if scope == MemoryScope.MEMBER:
            if member_id is None:
                raise MemoryPayloadInvalidError()
            _require_member_access(user, int(member_id))
        else:
            member_id = None
        if scope != MemoryScope.AGENT:
            agent_key = None
        if scope != MemoryScope.THREAD:
            thread_id = None

        layer = payload.get("layer") or (existing.layer if existing else MemoryLayer.L3)
        document_key = payload.get("document_key") or (existing.document_key if existing else "preferences")
        try:
            validate_layer_document(layer, document_key)
        except ValueError as exc:
            raise MemoryPayloadInvalidError() from exc
        if creating and not (scope == MemoryScope.ACCOUNT and layer == MemoryLayer.L3 and document_key == "preferences"):
            raise MemoryPayloadInvalidError()

        try:
            scope_key = compute_scope_key(scope=scope, member_id=member_id, agent_key=agent_key, thread_id=thread_id)
            section_key = validate_section_key(
                payload.get("section_key") or (existing.section_key if existing else "answer_style"),
                document_key=document_key,
            )
        except ValueError as exc:
            raise MemoryPayloadInvalidError() from exc

        memory_type = payload.get("memory_type") or (existing.memory_type if existing else MemoryType.PREFERENCE)
        if memory_type not in MemoryType.values:
            raise MemoryPayloadInvalidError()
        content = clamp_content(str(payload.get("content") or (existing.content if existing else "")))
        if not content:
            raise MemoryPayloadInvalidError()
        structured_value = payload.get("structured_value")
        if structured_value is None:
            structured_value = existing.structured_value if existing else {}
        if not isinstance(structured_value, dict):
            raise MemoryPayloadInvalidError()

        source = payload.get("source") or (existing.source if existing else MemorySource.USER)
        if source not in MemorySource.values:
            raise MemoryPayloadInvalidError()
        sensitivity = payload.get("sensitivity") or (existing.sensitivity if existing else MemorySensitivity.NORMAL)
        if sensitivity not in MemorySensitivity.values:
            raise MemoryPayloadInvalidError()
        confirmation_status = payload.get("confirmation_status") or (
            existing.confirmation_status if existing else MemoryConfirmationStatus.NOT_REQUIRED
        )
        if confirmation_status not in MemoryConfirmationStatus.values:
            raise MemoryPayloadInvalidError()
        status = payload.get("status") or (existing.status if existing else MemoryStatus.ACTIVE)
        if status not in MemoryStatus.values:
            raise MemoryPayloadInvalidError()

        normalized_key = compute_normalized_key(
            memory_type=memory_type,
            content=content,
            client_key=payload.get("normalized_key") or (existing.normalized_key if existing else None),
        )
        dedup_key = compute_dedup_key(
            user_id=user.id,
            scope_key=scope_key,
            layer=layer,
            document_key=document_key,
            memory_type=memory_type,
            normalized_key=normalized_key,
        )
        return {
            "scope": scope,
            "scope_key": scope_key,
            "member_id": member_id,
            "agent_key": agent_key,
            "thread_id": thread_id,
            "layer": layer,
            "document_key": document_key,
            "section_key": section_key,
            "memory_type": memory_type,
            "normalized_key": normalized_key,
            "dedup_key": dedup_key,
            "title": title_from_content(content, payload.get("title") or (existing.title if existing else None)),
            "content": content,
            "structured_value": structured_value,
            "is_pinned": bool(
                payload.get("is_pinned") if "is_pinned" in payload else (existing.is_pinned if existing else False)
            ),
            "sort_order": int(
                payload.get("sort_order")
                if payload.get("sort_order") is not None
                else (existing.sort_order if existing else 0)
            ),
            "content_hash": compute_content_hash(content=content, structured_value=structured_value),
            "source": source,
            "confirmation_status": confirmation_status,
            "sensitivity": sensitivity,
            "status": status,
            "expires_at": payload.get("expires_at") if "expires_at" in payload else (existing.expires_at if existing else None),
        }


def _lock_owned(user, memory_id, *, allow_deleted: bool = False) -> AIMemory:
    memory = AIMemory.objects.select_for_update().filter(user=user, id=memory_id).first()
    if memory is None:
        raise MemoryNotFoundError()
    if memory.is_deleted and not allow_deleted:
        raise MemoryDeletedError(snapshot=memory_to_snapshot(memory), reason_code="tombstoned")
    return memory


def _assert_revision(memory: AIMemory, base_revision) -> None:
    if base_revision is None:
        raise MemoryPayloadInvalidError()
    if int(memory.revision) != int(base_revision):
        raise MemoryRevisionConflictError(snapshot=memory_to_snapshot(memory), reason_code="revision_conflict")


def _require_member_access(user, member_id: int) -> None:
    try:
        from medical.services.member_permission_gate import MemberPermissionGate

        MemberPermissionGate.require_access(user, member_id)
    except MemberPermissionDenied as exc:
        raise MemoryScopeForbiddenError() from exc


def _accepted(memory: AIMemory, *, replayed: bool) -> dict[str, Any]:
    return {
        "status": "replayed" if replayed else "accepted",
        "replayed": replayed,
        "memory_id": str(memory.id),
        "revision": memory.revision,
        "snapshot": memory_to_snapshot(memory),
        "resolution": None,
        "reason_code": None,
    }
