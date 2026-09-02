from __future__ import annotations

import hashlib
import json
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import HospitalCareCommandReceipt


def request_hash(payload: dict[str, Any] | None) -> str:
    raw = json.dumps(payload or {}, cls=DjangoJSONEncoder, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_command_key(request) -> str:
    key = (request.headers.get("Idempotency-Key") or "").strip()
    if not key:
        raise HospitalCareError("IDEMPOTENCY_KEY_REQUIRED")
    if len(key) > 128:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "Idempotency-Key"})
    return key


class CommandIdempotency:
    @staticmethod
    def lookup(*, user, key: str, request_hash_value: str) -> HospitalCareCommandReceipt | None:
        receipt = HospitalCareCommandReceipt.objects.filter(actor_user=user, command_key=key).first()
        if receipt is None:
            return None
        if receipt.request_hash != request_hash_value:
            raise HospitalCareError("IDEMPOTENCY_CONFLICT")
        return receipt

    @staticmethod
    def record(
        *,
        user,
        key: str,
        request_hash_value: str,
        resource_type: str,
        resource_id: str,
        response_code: int,
        response_snapshot: dict[str, Any],
    ) -> HospitalCareCommandReceipt:
        return HospitalCareCommandReceipt.objects.create(
            actor_user=user,
            command_key=key,
            request_hash=request_hash_value,
            resource_type=resource_type,
            resource_id=str(resource_id),
            response_code=response_code,
            response_snapshot=response_snapshot,
        )


def run_idempotent_command(*, request, payload: dict[str, Any], resource_type: str, writer):
    key = resolve_command_key(request)
    digest = request_hash(payload)
    existing = CommandIdempotency.lookup(user=request.user, key=key, request_hash_value=digest)
    if existing is not None:
        return existing.response_snapshot, True
    with transaction.atomic():
        locked = (
            HospitalCareCommandReceipt.objects.select_for_update()
            .filter(actor_user=request.user, command_key=key)
            .first()
        )
        if locked is not None:
            if locked.request_hash != digest:
                raise HospitalCareError("IDEMPOTENCY_CONFLICT")
            return locked.response_snapshot, True
        snapshot, resource_id = writer()
        CommandIdempotency.record(
            user=request.user,
            key=key,
            request_hash_value=digest,
            resource_type=resource_type,
            resource_id=str(resource_id),
            response_code=0,
            response_snapshot=snapshot,
        )
        return snapshot, False
