from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from chat_sync.ai_memory.constants import RECEIPT_TTL_DAYS
from chat_sync.ai_models.memory import AIMemoryMutationReceipt

RECEIPT_TTL = timedelta(days=RECEIPT_TTL_DAYS)


class IdempotencyConflict(Exception):
    """Same mutation_id received with a different request body."""


def compute_request_hash(
    *,
    operation: str,
    memory_id: Any,
    base_revision: int | None,
    memory: dict[str, Any] | None,
) -> str:
    canonical = {
        "operation": operation,
        "memory_id": str(memory_id),
        "base_revision": base_revision,
        "memory": memory or {},
    }
    raw = json.dumps(
        canonical,
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class IdempotencyService:
    @staticmethod
    def find_receipt(*, user, mutation_id) -> AIMemoryMutationReceipt | None:
        return AIMemoryMutationReceipt.objects.filter(user=user, mutation_id=mutation_id).first()

    @staticmethod
    def check_replay(*, user, mutation_id, request_hash: str) -> AIMemoryMutationReceipt | None:
        receipt = IdempotencyService.find_receipt(user=user, mutation_id=mutation_id)
        if receipt is None:
            return None
        if receipt.request_hash != request_hash:
            raise IdempotencyConflict(f"mutation {mutation_id} replayed with a different request body")
        return receipt

    @staticmethod
    def record(
        *,
        user,
        mutation_id,
        memory_id,
        operation: str,
        request_hash: str,
        base_revision: int | None,
        result_revision: int,
        result_snapshot: dict[str, Any],
    ) -> AIMemoryMutationReceipt:
        return AIMemoryMutationReceipt.objects.create(
            user=user,
            mutation_id=mutation_id,
            memory_id=memory_id,
            operation=operation,
            request_hash=request_hash,
            base_revision=base_revision,
            result_revision=result_revision,
            result_snapshot=result_snapshot,
            expires_at=timezone.now() + RECEIPT_TTL,
        )
