"""快捷问题配置与生成记录后台序列化器（BACKOFFICE-CONVERSATION-000001）。"""

from rest_framework import serializers

from medical.models import ChatGuideGeneratedQuestionRecord, ChatGuideQuickQuestionConfig


def _prompt_preview(prompt: str, limit: int = 120) -> str:
    trimmed = (prompt or "").strip()
    if len(trimmed) <= limit:
        return trimmed
    return trimmed[:limit] + "…"


class QuickQuestionConfigSerializer(serializers.ModelSerializer):
    prompt_preview = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source="created_by.username", read_only=True, default="")
    updated_by_name = serializers.CharField(source="updated_by.username", read_only=True, default="")

    class Meta:
        model = ChatGuideQuickQuestionConfig
        fields = (
            "id",
            "title",
            "prompt",
            "prompt_preview",
            "category",
            "locale",
            "is_active",
            "metadata",
            "created_by",
            "created_by_name",
            "updated_by",
            "updated_by_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )

    def get_prompt_preview(self, obj):
        return _prompt_preview(obj.prompt)


class QuickQuestionConfigCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatGuideQuickQuestionConfig
        fields = ("title", "prompt", "category", "locale", "is_active", "metadata")


class QuickQuestionConfigUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatGuideQuickQuestionConfig
        fields = ("title", "prompt", "category", "locale", "metadata")


class GeneratedQuestionRecordSerializer(serializers.ModelSerializer):
    prompt_preview = serializers.SerializerMethodField()
    user_name = serializers.CharField(source="user.username", read_only=True, default="")
    member_name = serializers.CharField(source="member.name", read_only=True, default="")

    class Meta:
        model = ChatGuideGeneratedQuestionRecord
        fields = (
            "id",
            "title",
            "prompt",
            "prompt_preview",
            "category",
            "user",
            "user_name",
            "member",
            "member_name",
            "click_count",
            "created_at",
            "updated_at",
        )

    def get_prompt_preview(self, obj):
        return _prompt_preview(obj.prompt)