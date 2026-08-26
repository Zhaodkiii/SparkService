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


class KnowledgeIndexStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"
    STALE = "stale", "Stale"


class KnowledgeBase(models.Model):
    """知识库容器；V1 每账号恰好一个 `is_default=True` 的个人知识库。

    `default_slot` 是 MySQL 安全的默认库唯一性哨兵：默认库写入固定值 1，
    非默认库写入 NULL（MySQL 允许多行 NULL），配合 `UniqueConstraint(user, default_slot)`
    在数据库层面保证同一账号最多一个默认知识库，避免只靠应用层先查后建产生并发重复。
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
    """知识文档；`id` 由客户端生成并跨设备保持稳定，服务端不会重新分配。"""

    id = models.UUIDField(primary_key=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_documents")
    knowledge_base = models.ForeignKey(KnowledgeBase, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=255, default="")
    content = models.TextField(blank=True, default="")
    excerpt = models.TextField(blank=True, default="")
    scope = models.CharField(max_length=32, choices=KnowledgeDocumentScope.choices, default=KnowledgeDocumentScope.PERSONAL)
    bound_model_id = models.CharField(max_length=128, null=True, blank=True)
    source = models.CharField(max_length=16, choices=KnowledgeDocumentSource.choices, default=KnowledgeDocumentSource.USER)
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


class KnowledgeChunk(models.Model):
    """服务端派生的检索单元（P2）；本次仅建模，索引流水线不在本轮范围内。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name="chunks")
    document_revision = models.BigIntegerField(default=0)
    sequence = models.IntegerField(default=0)
    content = models.TextField(blank=True, default="")
    content_hash = models.CharField(max_length=64, default="")
    token_count = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    vector_ref = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_sync_ai_knowledge_chunk"
        constraints = [
            models.UniqueConstraint(fields=("document", "document_revision", "sequence"), name="uniq_kchunk_doc_rev_seq"),
        ]
        indexes = [
            models.Index(fields=["document", "document_revision"], name="idx_kchunk_doc_rev"),
        ]


class KnowledgeIndexState(models.Model):
    """文档索引状态（P2）；索引失败不回滚文档同步，本次仅建模不写入。"""

    id = models.BigAutoField(primary_key=True)
    document = models.OneToOneField(KnowledgeDocument, on_delete=models.CASCADE, related_name="index_state")
    document_revision = models.BigIntegerField(default=0)
    status = models.CharField(max_length=16, choices=KnowledgeIndexStatus.choices, default=KnowledgeIndexStatus.PENDING, db_index=True)
    chunk_count = models.IntegerField(default=0)
    embedding_provider = models.CharField(max_length=128, blank=True, default="")
    embedding_model = models.CharField(max_length=128, blank=True, default="")
    embedding_dimension = models.IntegerField(null=True, blank=True)
    embedding_signature = models.CharField(max_length=255, blank=True, default="")
    index_version = models.CharField(max_length=64, blank=True, default="")
    last_error_code = models.CharField(max_length=128, null=True, blank=True)
    indexed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_sync_ai_knowledge_index_state"


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
