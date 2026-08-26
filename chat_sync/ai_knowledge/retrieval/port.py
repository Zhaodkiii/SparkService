from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class KnowledgeRetrievalUnavailable(Exception):
    """检索后端暂不可用；`code` 供调用方原样映射为对话侧的业务错误码。"""

    def __init__(self, code: str = "chat_knowledge_backend_unavailable"):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ResolvedKnowledgeChunk:
    """检索结果的最小契约，供 `chat_sync.ai_services.context` 转换为 `ResolvedSource`。"""

    chunk_id: str
    document_id: str
    document_revision: int
    title: str
    content: str
    content_hash: str
    index_version: str
    metadata: dict[str, Any]


class KnowledgeRetrievalPort(Protocol):
    """P2 检索端口：本轮只冻结接口与调用点，不接入任何向量库/索引流水线。"""

    def resolve_chunk(self, *, user, chunk_id: str, revision: int | None = None) -> ResolvedKnowledgeChunk:
        """按 chunk_id 解析单条知识片段；必须重新校验账号归属、墓碑与索引状态。"""
        ...

    def search(
        self,
        *,
        user,
        base_ids: list[str],
        query: str,
        top_k: int = 8,
        threshold: float = 0.75,
    ) -> list[ResolvedKnowledgeChunk]:
        """按知识库范围做语义/词法检索；P2 未实现前始终返回空列表。"""
        ...
