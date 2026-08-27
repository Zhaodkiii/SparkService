from __future__ import annotations

from rest_framework import serializers

MAX_MUTATIONS_PER_BATCH = 50
OPERATION_CHOICES = ("create", "update", "delete", "restore")


class KnowledgeMutationDocumentSerializer(serializers.Serializer):
    """create/update 携带的文档完整快照；delete/restore 不需要该字段。"""

    title = serializers.CharField(required=False, allow_blank=True, default="")
    content = serializers.CharField(required=False, allow_blank=True, default="")
    excerpt = serializers.CharField(required=False, allow_blank=True, default="")
    scope = serializers.CharField(required=False, allow_blank=True, default="personal")
    bound_model_id = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    source = serializers.CharField(required=False, allow_blank=True, default="user")
    client_created_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    client_updated_at = serializers.DateTimeField(required=False, allow_null=True, default=None)


class KnowledgeMutationClientSerializer(serializers.Serializer):
    platform = serializers.CharField(required=False, allow_blank=True, default="")
    version = serializers.CharField(required=False, allow_blank=True, default="")
    device_id = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)


class KnowledgeSyncMutationSerializer(serializers.Serializer):
    mutation_id = serializers.UUIDField()
    document_id = serializers.UUIDField()
    operation = serializers.ChoiceField(choices=OPERATION_CHOICES)
    base_revision = serializers.IntegerField(required=False, allow_null=True, default=None)
    knowledge_base_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    document = KnowledgeMutationDocumentSerializer(required=False)
    client = KnowledgeMutationClientSerializer(required=False)

    def validate(self, attrs):
        operation = attrs.get("operation")
        if operation in ("create", "update") and not attrs.get("document"):
            raise serializers.ValidationError({"document": "required for create/update mutations"})
        if operation in ("update", "delete", "restore") and attrs.get("base_revision") is None:
            raise serializers.ValidationError({"base_revision": "required for update/delete/restore mutations"})
        return attrs


class KnowledgeSyncPushRequestSerializer(serializers.Serializer):
    mutations = KnowledgeSyncMutationSerializer(many=True, allow_empty=False)

    def validate_mutations(self, value):
        if len(value) > MAX_MUTATIONS_PER_BATCH:
            raise serializers.ValidationError(f"at most {MAX_MUTATIONS_PER_BATCH} mutations per push batch")
        return value


class RetrievalConfigSerializer(serializers.Serializer):
    top_k = serializers.IntegerField(required=False, min_value=1, max_value=20)
    score_threshold = serializers.FloatField(required=False, min_value=0, max_value=1)
    rerank_enabled = serializers.BooleanField(required=False)


class KnowledgeBaseCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    kind = serializers.CharField(required=False, default="personal")
    make_default = serializers.BooleanField(required=False, default=False)
    retrieval_config = RetrievalConfigSerializer(required=False)


class KnowledgeBaseUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, max_length=128)
    make_default = serializers.BooleanField(required=False)
    retrieval_config = RetrievalConfigSerializer(required=False)
    revision = serializers.IntegerField(required=False)


class KnowledgeDocumentWriteSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    content = serializers.CharField(required=False, allow_blank=True)
    scope = serializers.CharField(required=False, default="personal")
    source = serializers.CharField(required=False, default="user")
    revision = serializers.IntegerField(required=False)


class KnowledgeFileBindSerializer(serializers.Serializer):
    file_uuid = serializers.UUIDField()
    reuse = serializers.BooleanField(required=False, default=False)


class KnowledgeSearchSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=2000)
    knowledge_base_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    top_k = serializers.IntegerField(required=False, min_value=1, max_value=20)
    score_threshold = serializers.FloatField(required=False, min_value=0, max_value=1)
