from __future__ import annotations

from typing import Any

from common.exceptions import APIError

ERROR_MESSAGES: dict[str, str] = {
    "knowledge_base_not_found": "知识库不存在或无权访问。",
    "knowledge_base_forbidden": "无权访问该知识库。",
    "knowledge_base_deleted": "知识库已删除。",
    "knowledge_base_revision_conflict": "知识库已被其他设备更新，请刷新后重试。",
    "knowledge_base_quota_exceeded": "已达到个人知识库数量上限。",
    "knowledge_base_default_undeletable": "默认知识库不可删除。",
    "knowledge_document_not_found": "文档不存在或无权访问。",
    "knowledge_document_revision_conflict": "文档已被其他设备更新，请刷新后重试。",
    "knowledge_document_deleted": "文档已删除。",
    "knowledge_idempotency_conflict": "幂等键已用于不同请求。",
    "knowledge_payload_invalid": "请求参数无效。",
}

STATUS_BY_CODE: dict[str, int] = {
    "knowledge_base_not_found": 404,
    "knowledge_base_forbidden": 403,
    "knowledge_base_deleted": 404,
    "knowledge_base_revision_conflict": 409,
    "knowledge_base_quota_exceeded": 400,
    "knowledge_base_default_undeletable": 400,
    "knowledge_document_not_found": 404,
    "knowledge_document_revision_conflict": 409,
    "knowledge_document_deleted": 409,
    "knowledge_idempotency_conflict": 409,
    "knowledge_payload_invalid": 400,
}


class KnowledgeError(APIError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None, status_code: int | None = None):
        payload = {"error_code": code, **(details or {})}
        super().__init__(
            ERROR_MESSAGES.get(code, code),
            code=-1,
            status_code=status_code or STATUS_BY_CODE.get(code, 400),
            details=payload,
        )
        self.error_code = code
