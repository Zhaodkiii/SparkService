from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class KnowledgeBaseKind(models.TextChoices):
    PERSONAL = "personal", "Personal"
    SHARED = "shared", "Shared"
    SYSTEM = "system", "System"
    IMPORTED = "imported", "Imported"


class KnowledgeDocumentScope(models.TextChoices):
    PERSONAL = "personal", "Personal"
    AGENT_BOUND = "agent_bound", "Agent Bound"


class KnowledgeDocumentSource(models.TextChoices):
    USER = "user", "User"
    TOOL = "tool", "Tool"
    IMPORT = "import", "Import"
    WEB = "web", "Web"


class KnowledgeMutationOperation(models.TextChoices):
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    RESTORE = "restore", "Restore"


class KnowledgeSyncStatus(models.TextChoices):
    SYNCED = "synced", "Synced"
    PENDING = "pending", "Pending"
    FAILED = "failed", "Failed"
    CONFLICT = "conflict", "Conflict"


def default_retrieval_config() -> dict:
    """Kept for historical migration 0014 import path only."""
    return {"top_k": 6, "score_threshold": 0.72, "rerank_enabled": False}


class KnowledgeBase(models.Model):
    """知识库容器；每账号恰好一个 `is_default=True` 的个人知识库。

    `default_slot` 是 MySQL 安全的默认库唯一性哨兵：默认库写入固定值 1，
    非默认库写入 NULL（MySQL 允许多行 NULL），配合 `UniqueConstraint(user, default_slot)`
    在数据库层面保证同一账号最多一个默认知识库。
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_bases")
    name = models.CharField(max_length=128, default="个人知识库")
    kind = models.CharField(max_length=16, choices=KnowledgeBaseKind.choices, default=KnowledgeBaseKind.PERSONAL)
    is_default = models.BooleanField(default=False)
    default_slot = models.PositiveSmallIntegerField(null=True, blank=True)
    revision = models.BigIntegerField(default=1)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    server_updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "chat_sync_ai_knowledge_base"
        constraints = [
            models.UniqueConstraint(fields=("user", "id"), name="uniq_kbase_user_id"),
            models.UniqueConstraint(fields=("user", "default_slot"), name="uniq_kbase_user_default_slot"),
        ]
        indexes = [
            models.Index(fields=["user", "server_updated_at", "id"], name="idx_kbase_user_sync"),
        ]


class KnowledgeDocument(models.Model):
    """知识文档；`id` 由客户端或 Web 生成并跨设备保持稳定。"""

    id = models.UUIDField(primary_key=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_documents")
    knowledge_base = models.ForeignKey(KnowledgeBase, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=255, default="")
    content = models.TextField(blank=True, default="")
    excerpt = models.TextField(blank=True, default="")
    scope = models.CharField(max_length=32, choices=KnowledgeDocumentScope.choices, default=KnowledgeDocumentScope.PERSONAL)
    bound_model_id = models.CharField(max_length=128, null=True, blank=True)
    source = models.CharField(max_length=16, choices=KnowledgeDocumentSource.choices, default=KnowledgeDocumentSource.USER)
    source_file_uuid = models.UUIDField(null=True, blank=True, db_index=True)
    revision = models.BigIntegerField(default=1)
    content_hash = models.CharField(max_length=64, default="")
    origin_device_id_hash = models.CharField(max_length=64, null=True, blank=True)
    last_device_id_hash = models.CharField(max_length=64, null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    client_created_at = models.DateTimeField(null=True, blank=True)
    client_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    server_updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "chat_sync_ai_knowledge_document"
        constraints = [
            models.UniqueConstraint(fields=("user", "id"), name="uniq_kdoc_user_id"),
        ]
        indexes = [
            models.Index(fields=["user", "server_updated_at", "id"], name="idx_kdoc_user_sync"),
            models.Index(fields=["user", "knowledge_base", "is_deleted", "server_updated_at"], name="idx_kdoc_base_sync"),
        ]


class KnowledgeMutationReceipt(models.Model):
    """Push 幂等回执：`(user, mutation_id)` 唯一，命中且 `request_hash` 相同即回放原 ACK。"""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_mutation_receipts")
    mutation_id = models.UUIDField()
    document_id = models.UUIDField(db_index=True)
    operation = models.CharField(max_length=16, choices=KnowledgeMutationOperation.choices)
    request_hash = models.CharField(max_length=64)
    result_revision = models.BigIntegerField(default=0)
    response_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "chat_sync_ai_knowledge_mutation_receipt"
        constraints = [
            models.UniqueConstraint(fields=("user", "mutation_id"), name="uniq_kreceipt_user_mutation"),
        ]
        indexes = [
            models.Index(fields=["user", "document_id"], name="idx_kreceipt_user_doc"),
        ]


class KnowledgeCommandReceipt(models.Model):
    """Web 管理写入的 Idempotency-Key 回执。"""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_command_receipts")
    idempotency_key = models.CharField(max_length=128)
    operation = models.CharField(max_length=64)
    request_hash = models.CharField(max_length=64)
    status_code = models.PositiveSmallIntegerField(default=200)
    response_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "chat_sync_ai_knowledge_command_receipt"
        constraints = [
            models.UniqueConstraint(fields=("user", "idempotency_key"), name="uniq_kcmd_user_idempotency"),
        ]
