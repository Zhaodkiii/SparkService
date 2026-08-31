from __future__ import annotations

from typing import Any

from common.exceptions import APIError

ERROR_MESSAGES: dict[str, str] = {
    "memory_not_found": "记忆不存在或无权访问。",
    "memory_mutation_reused": "幂等键已用于不同请求。",
    "memory_duplicate_key": "已存在等价记忆。",
    "memory_tombstoned": "目标记忆已删除。",
    "memory_scope_forbidden": "无权访问该成员或会话记忆。",
    "memory_payload_invalid": "请求参数无效。",
    "memory_operation_unsupported": "该记忆操作已不再支持。",
    "memory_revision_required": "更新或删除记忆需要携带当前 revision。",
    "memory_revision_conflict": "记忆版本已过期，请使用服务端快照。",
}

STATUS_BY_CODE: dict[str, int] = {
    "memory_not_found": 404,
    "memory_mutation_reused": 409,
    "memory_duplicate_key": 409,
    "memory_tombstoned": 409,
    "memory_scope_forbidden": 403,
    "memory_payload_invalid": 400,
    "memory_operation_unsupported": 400,
    "memory_revision_required": 428,
    "memory_revision_conflict": 409,
}


class MemoryError(APIError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None, status_code: int | None = None):
        payload = {"error_code": code, **(details or {})}
        super().__init__(
            ERROR_MESSAGES.get(code, code),
            code=-1,
            status_code=status_code or STATUS_BY_CODE.get(code, 400),
            details=payload,
        )
        self.error_code = code
