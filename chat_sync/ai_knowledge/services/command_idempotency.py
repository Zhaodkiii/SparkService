from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from chat_sync.ai_models.knowledge import KnowledgeCommandReceipt
from chat_sync.ai_knowledge.errors import KnowledgeError

from .idempotency_service import RECEIPT_TTL
import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder


def command_request_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class CommandIdempotencyService:
    @staticmethod
    def lookup(*, user, key: str | None, request_hash: str) -> KnowledgeCommandReceipt | None:
        if not key:
            return None
        receipt = KnowledgeCommandReceipt.objects.filter(user=user, idempotency_key=key).first()
        if receipt is None:
            return None
        if receipt.request_hash != request_hash:
            raise KnowledgeError("knowledge_idempotency_conflict")
        return receipt

    @staticmethod
    def record(*, user, key: str, operation: str, request_hash: str, status_code: int, response_snapshot: dict[str, Any]) -> KnowledgeCommandReceipt:
        return KnowledgeCommandReceipt.objects.create(
            user=user,
            idempotency_key=key,
            operation=operation,
            request_hash=request_hash,
            status_code=status_code,
            response_snapshot=response_snapshot,
            expires_at=timezone.now() + timedelta(days=RECEIPT_TTL.days),
        )
