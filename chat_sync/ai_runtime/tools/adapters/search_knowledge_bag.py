from __future__ import annotations

import hashlib
import time
from uuid import UUID

from asgiref.sync import sync_to_async
from django.conf import settings

from chat_sync.ai_knowledge.api.dto import citation_to_dto, relevance_label
from chat_sync.ai_knowledge.retrieval.port import KnowledgeRetrievalUnavailable
from chat_sync.ai_knowledge.retrieval.service import get_retrieval_port
from chat_sync.ai_models.knowledge import KnowledgeRetrievalAudit
from chat_sync.ai_runtime.protocols.tool_protocol import BaseTool, ToolDefinition, ToolResult
from chat_sync.ai_runtime.tools.adapters._common import safe_text
from chat_sync.ai_runtime.tools.policy import ToolExecutionContext


class SearchKnowledgeBagTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_knowledge_bag",
            description="在用户已选择的知识库中检索相关资料，返回带来源的摘录。未选择知识库时不要调用。",
            raw_parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索问题"},
                    "knowledge_base_ids": {"type": "array", "items": {"type": "string"}},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
                    "score_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        )

    async def execute(self, *, query: str = "", knowledge_base_ids=None, top_k=None, score_threshold=None, _execution_context=None, **kwargs) -> ToolResult:
        if not isinstance(_execution_context, ToolExecutionContext):
            return ToolResult(content="工具执行上下文不可用。", success=False, metadata={"error_code": "tool_context_missing", "activity_status": "failed"})
        if not getattr(settings, "KNOWLEDGE_RAG_TOOL_ENABLED", False):
            return ToolResult(content="知识检索功能未开启。", success=True, metadata={"activity_status": "skipped", "skip_reason": "feature_disabled"})
        started = time.monotonic()
        selected = await sync_to_async(_selected_base_ids)(_execution_context, knowledge_base_ids)
        if not selected:
            return ToolResult(content="当前对话未选择可检索的知识库。", success=True, metadata={"activity_status": "skipped", "skip_reason": "no_ready_knowledge_base"})
        limited_k = max(1, min(int(top_k or 8), 20))
        threshold = max(0.0, min(float(score_threshold if score_threshold is not None else 0.55), 1.0))
        try:
            hits = await sync_to_async(get_retrieval_port().search)(
                user=await sync_to_async(_load_user)(_execution_context.user_id),
                base_ids=selected,
                query=str(query or "").strip()[:2000],
                top_k=limited_k,
                threshold=threshold,
            )
        except KnowledgeRetrievalUnavailable as exc:
            await sync_to_async(_audit)(_execution_context, selected, query, limited_k, threshold, 0, "failed", exc.code, started)
            return ToolResult(content="未检索到可用资料。", success=True, metadata={"activity_status": "failed", "error_code": "knowledge_retrieval_unavailable"})
        citations = [
            citation_to_dto(
                citation_id=f"cite_{index}",
                knowledge_base_id=str(item.metadata.get("knowledge_base_id") or ""),
                knowledge_base_name=str(item.metadata.get("knowledge_base_name") or ""),
                document_id=item.document_id,
                document_title=item.title,
                chunk_id=item.chunk_id,
                chunk_revision=item.document_revision,
                index_version=item.index_version,
                snippet=safe_text(item.content, 400),
                relevance=relevance_label(float(item.metadata.get("score") or 0)),
            )
            for index, item in enumerate(hits, start=1)
        ]
        status = "empty" if not citations else "succeeded"
        await sync_to_async(_audit)(_execution_context, selected, query, limited_k, threshold, len(citations), status, "", started)
        lines = [f"[{item['citation_id']}] {item['document_title']}: {item['snippet']}" for item in citations]
        content = "\n".join(lines) if lines else "未检索到可用资料。"
        return ToolResult(
            content=content,
            success=True,
            sources=[{"source_id": item["chunk_id"], "type": "knowledge_chunk", "title": item["document_title"]} for item in citations],
            metadata={
                "activity_status": status,
                "citations": citations,
                "hit_count": len(citations),
                "selected_knowledge_base_ids": selected,
                "top_k": limited_k,
                "score_threshold": threshold,
            },
        )


def _load_user(user_id: int):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.get(pk=user_id)


def _selected_base_ids(context: ToolExecutionContext, requested) -> list[str]:
    from chat_sync.ai_models import ChatRun, ChatTurnContextSnapshot
    from chat_sync.ai_knowledge.services.preference_validation import freeze_knowledge_bases

    run = ChatRun.objects.filter(pk=context.run_id).select_related("user").first()
    if run is None:
        return []
    snapshot = ChatTurnContextSnapshot.objects.filter(run=run).first()
    frozen = []
    if snapshot and isinstance(snapshot.sources, list):
        frozen = [item.get("source_id") for item in snapshot.sources if isinstance(item, dict) and item.get("type") == "knowledge_base"]
    prefs = (run.request_snapshot or {}).get("preferences") or {}
    ids = requested or frozen or prefs.get("knowledge_bases") or []
    user = run.user
    eligible = [item["id"] for item in freeze_knowledge_bases(user, ids) if item.get("retrieval_eligible")]
    return eligible


def _audit(context: ToolExecutionContext, base_ids, query, top_k, threshold, hit_count, outcome, error_code, started):
    KnowledgeRetrievalAudit.objects.create(
        user_id=context.user_id,
        run_id=context.run_id,
        knowledge_base_ids=list(base_ids),
        query_hash=hashlib.sha256(str(query or "").encode("utf-8")).hexdigest(),
        top_k=top_k,
        score_threshold=threshold,
        hit_count=hit_count,
        duration_ms=int((time.monotonic() - started) * 1000),
        outcome=outcome,
        error_code=error_code or "",
    )


__all__ = ["SearchKnowledgeBagTool"]
