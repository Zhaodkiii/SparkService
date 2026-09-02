"""CHAT-000055：患者端会话能力 + 医院知识 Manifest / 增量 pull 查询。

患者端只读契约：
- conversation context 携带 capabilities 与 knowledge_manifest（Q22）。
- 按 knowledge_base_id 增量 pull（Q23）：首次 cursor 为空返回全量快照，
  后续使用服务端 opaque cursor 增量拉取；删除以 tombstone（is_deleted=true）下发。
- 向量只在 profile.vector_status == current 且 indexed_revision == kb.revision、
  且 chunk.document_revision == document.revision 时下发；其余情况 chunks 为空，
  客户端降级关键词检索（Q32/Q33 的向量有效性门禁在客户端再校验一次）。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json

from django.utils.dateparse import parse_datetime

from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeDocument

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    ClinicalAgentKnowledgeBinding,
    ClinicalAgentProfile,
    ClinicalConversationBinding,
    HospitalKnowledgeBaseProfile,
    HospitalKnowledgeChunk,
)

DEFAULT_PULL_LIMIT = 100
MAX_PULL_LIMIT = 200


def conversation_capabilities(binding: ClinicalConversationBinding) -> dict:
    """Q27/Q28：会话能力单一事实源。

    - 智能体下架：历史可读、禁止发送、停止知识同步。
    - 成员权限撤回由 patient_catalog.get_patient_conversation 在查询阶段
      抛出 MEMBER_ACCESS_DENIED；进入此函数即视为成员仍有效。
    """
    agent = binding.agent
    published = agent.publication_status == ClinicalAgentProfile.PublicationStatus.PUBLISHED
    ended = binding.service_status == ClinicalConversationBinding.ServiceStatus.ENDED
    can_send = published and ended is False
    return {
        "can_read_cached_history": True,
        "can_pull_remote_messages": published,
        "can_send_message": can_send,
        "can_sync_knowledge": published,
        "read_only_reason": None if published else "agent_unpublished",
    }


def agent_knowledge_manifest(agent: ClinicalAgentProfile) -> dict | None:
    """Q22/Q34：按当前生效绑定实时计算 Manifest。

    manifest_revision 由绑定集合（KB ID、状态、排序、绑定更新时间）哈希生成；
    解绑、新增、排序变化都会导致 revision 变化。
    智能体下架时返回 None，客户端据此停止知识同步。
    """
    if agent.publication_status != ClinicalAgentProfile.PublicationStatus.PUBLISHED:
        return None
    bindings = list(
        ClinicalAgentKnowledgeBinding.objects.filter(
            agent_id=agent.id,
            status=ClinicalAgentKnowledgeBinding.Status.ACTIVE,
        ).order_by("sort_order", "id")
    )
    if not bindings:
        return None

    kb_ids = [item.knowledge_base_id for item in bindings]
    kb_map = {str(item.id): item for item in KnowledgeBase.objects.filter(pk__in=kb_ids)}
    profile_map = {
        str(item.knowledge_base_id): item
        for item in HospitalKnowledgeBaseProfile.objects.filter(
            knowledge_base_id__in=kb_ids,
            is_deleted=False,
            hospital_id=agent.hospital_id,
        )
    }

    fingerprint_source = "|".join(
        f"{item.knowledge_base_id}:{item.sort_order}:{item.status}:{item.updated_at.isoformat()}"
        for item in bindings
    )
    manifest_revision = int(hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:15], 16)

    items = []
    generated_at = None
    for item in bindings:
        key = str(item.knowledge_base_id)
        kb = kb_map.get(key)
        if kb is None or kb.is_deleted:
            # KB 已被全局删除：以解绑语义通知客户端清理 scope。
            items.append(
                {
                    "knowledge_base_id": key,
                    "name": "",
                    "revision": 0,
                    "vector_status": HospitalKnowledgeBaseProfile.VectorStatus.NOT_BUILT,
                    "indexed_revision": None,
                    "updated_at": None,
                    "deleted": True,
                }
            )
            continue
        profile = profile_map.get(key)
        vector_status = profile.vector_status if profile else HospitalKnowledgeBaseProfile.VectorStatus.NOT_BUILT
        indexed_revision = profile.indexed_revision if profile else None
        if generated_at is None or kb.server_updated_at > generated_at:
            generated_at = kb.server_updated_at
        items.append(
            {
                "knowledge_base_id": key,
                "name": profile.name if profile else kb.name,
                "revision": int(kb.revision or 1),
                "vector_status": vector_status,
                "indexed_revision": indexed_revision,
                "updated_at": kb.server_updated_at.isoformat() if kb.server_updated_at else None,
                "deleted": False,
            }
        )

    return {
        "manifest_revision": manifest_revision,
        "generated_at": generated_at.isoformat() if generated_at else agent.updated_at.isoformat(),
        "agent_id": str(agent.id),
        "hospital_id": str(agent.hospital_id),
        "knowledge_bases": items,
    }


def _encode_cursor(document: KnowledgeDocument) -> str:
    payload = {
        "updated_at": document.server_updated_at.isoformat() if document.server_updated_at else None,
        "id": str(document.id),
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _decode_cursor(raw: str):
    try:
        data = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))
        updated_at = parse_datetime(data["updated_at"])
        document_id = data["id"]
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_CURSOR_INVALID") from exc
    if updated_at is None:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_CURSOR_INVALID")
    return updated_at, document_id


def pull_knowledge_base_delta(*, knowledge_base_id, cursor: str | None, limit: int | None) -> dict:
    """Q23/Q36：按 KB ID 的只读增量 pull。

    - Demo 授权口径：登录即可读未删除医院科普库，不做 agent 绑定授权（Q24）。
    - 返回包含 tombstone（is_deleted=true）的文档，客户端据此清理本地缓存。
    - cursor 失效抛 HOSPITAL_KNOWLEDGE_CURSOR_INVALID，客户端清 cursor 后重做全量。
    """
    profile = (
        HospitalKnowledgeBaseProfile.objects.select_related("hospital", "embedding_binding")
        .filter(knowledge_base_id=knowledge_base_id, is_deleted=False, hospital__status="active")
        .first()
    )
    if profile is None:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_NOT_FOUND")
    knowledge_base = KnowledgeBase.objects.filter(pk=profile.knowledge_base_id, is_deleted=False).first()
    if knowledge_base is None:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_NOT_FOUND")

    page_size = max(1, min(int(limit or DEFAULT_PULL_LIMIT), MAX_PULL_LIMIT))
    qs = KnowledgeDocument.objects.filter(knowledge_base_id=knowledge_base.id).order_by("server_updated_at", "id")
    if cursor:
        updated_at, document_id = _decode_cursor(cursor)
        qs = qs.filter(server_updated_at__gte=updated_at).exclude(
            server_updated_at=updated_at,
            id__lte=document_id,
        )

    rows = list(qs[: page_size + 1])
    has_more = len(rows) > page_size
    rows = rows[:page_size]

    # 向量只在完全新鲜时下发：profile 为 current 且 indexed_revision 覆盖当前 KB revision。
    vectors_fresh = (
        profile.vector_status == HospitalKnowledgeBaseProfile.VectorStatus.CURRENT
        and profile.indexed_revision is not None
        and int(profile.indexed_revision) == int(knowledge_base.revision or 1)
    )
    chunk_map: dict[str, list[HospitalKnowledgeChunk]] = {}
    if vectors_fresh and rows:
        document_ids = [item.id for item in rows if item.is_deleted is False]
        for chunk in HospitalKnowledgeChunk.objects.filter(
            profile=profile,
            document_id__in=document_ids,
        ).order_by("chunk_index"):
            chunk_map.setdefault(str(chunk.document_id), []).append(chunk)

    documents = []
    for document in rows:
        chunks = []
        if document.is_deleted is False and vectors_fresh:
            for chunk in chunk_map.get(str(document.id), []):
                if int(chunk.document_revision) != int(document.revision):
                    # 旧 revision 向量不得冒充新正文向量。
                    continue
                chunks.append(
                    {
                        "id": str(chunk.id),
                        "sequence": chunk.chunk_index,
                        "content": chunk.content,
                        "content_hash": chunk.content_hash,
                        "document_revision": int(chunk.document_revision),
                        "vector_payload": chunk.vector_payload or [],
                        "embedding_binding_id": chunk.embedding_binding_id,
                    }
                )
        documents.append(
            {
                "id": str(document.id),
                "title": document.title,
                "content": "" if document.is_deleted else document.content,
                "excerpt": "" if document.is_deleted else document.excerpt,
                "revision": int(document.revision or 1),
                "is_deleted": document.is_deleted,
                "updated_at": document.server_updated_at.isoformat() if document.server_updated_at else None,
                "chunks": chunks,
            }
        )

    next_cursor = _encode_cursor(rows[-1]) if rows else cursor
    return {
        "knowledge_base_id": str(knowledge_base.id),
        "revision": int(knowledge_base.revision or 1),
        "vector_status": profile.vector_status,
        "indexed_revision": profile.indexed_revision,
        "cursor": next_cursor,
        "has_more": has_more,
        "documents": documents,
    }
