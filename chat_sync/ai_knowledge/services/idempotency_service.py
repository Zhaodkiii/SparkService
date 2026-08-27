from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from chat_sync.ai_models.knowledge import KnowledgeMutationReceipt

# D8：幂等回执至少保留 30 天，覆盖长期离线设备的 Outbox 重放需求。
RECEIPT_TTL = timedelta(days=30)


class IdempotencyConflict(Exception):
    """同一 mutation_id 收到了内容不同的请求体（客户端契约违规）。"""


def compute_request_hash(
    *,
    operation: str,
    document_id: Any,
    base_revision: int | None,
    document: dict[str, Any] | None,
) -> str:
    canonical = {
        "operation": operation,
        "document_id": str(document_id),
        "base_revision": base_revision,
        "document": document or {},
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
    def find_receipt(*, user, mutation_id) -> KnowledgeMutationReceipt | None:
        return KnowledgeMutationReceipt.objects.filter(user=user, mutation_id=mutation_id).first()

    @staticmethod
    def check_replay(*, user, mutation_id, request_hash: str) -> KnowledgeMutationReceipt | None:
        """命中且 hash 一致 → 返回回执用于回放 ACK；命中但 hash 不同 → 抛契约冲突；未命中 → None。"""
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
        document_id,
        operation: str,
        request_hash: str,
        result_revision: int,
        response_snapshot: dict[str, Any],
    ) -> KnowledgeMutationReceipt:
        return KnowledgeMutationReceipt.objects.create(
            user=user,
            mutation_id=mutation_id,
            document_id=document_id,
            operation=operation,
            request_hash=request_hash,
            result_revision=result_revision,
            response_snapshot=response_snapshot,
            expires_at=timezone.now() + RECEIPT_TTL,
        )
