from django.contrib.auth import get_user_model
from rest_framework import serializers

from content.models import ContentArticle, ContentArticleVersion, ContentCategory, ContentTag
from content.services import LOCALE_RE, SLUG_RE


User = get_user_model()


class ContentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentCategory
        fields = ("id", "name", "slug", "parent_id", "description", "sort_order", "is_active", "created_at", "updated_at")

    def validate_slug(self, value):
        if not SLUG_RE.match(value):
            raise serializers.ValidationError("invalid_slug")
        return value


class ContentTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentTag
        fields = ("id", "name", "slug", "description", "article_count", "is_active", "created_at", "updated_at")
        read_only_fields = ("article_count",)

    def validate_slug(self, value):
        if not SLUG_RE.match(value):
            raise serializers.ValidationError("invalid_slug")
        return value


class ContentArticleTagBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentTag
        fields = ("id", "name", "slug")


class ContentArticleCategoryBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentCategory
        fields = ("id", "name", "slug")


class AdminContentArticleListSerializer(serializers.ModelSerializer):
    category = ContentArticleCategoryBriefSerializer(read_only=True)
    tags = ContentArticleTagBriefSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    visibility_label = serializers.CharField(source="get_visibility_display", read_only=True)
    author_name = serializers.CharField(source="author.username", read_only=True)
    last_editor_name = serializers.CharField(source="last_editor.username", read_only=True)
    average_reading_time_seconds = serializers.SerializerMethodField()

    class Meta:
        model = ContentArticle
        fields = (
            "id",
            "title",
            "slug",
            "locale",
            "translation_group_id",
            "summary",
            "cover_image",
            "category",
            "tags",
            "status",
            "status_label",
            "visibility",
            "visibility_label",
            "is_top",
            "is_recommended",
            "view_count",
            "read_count",
            "reading_time_seconds",
            "average_reading_time_seconds",
            "author_name",
            "last_editor_name",
            "published_at",
            "updated_at",
            "deleted_at",
        )

    def get_average_reading_time_seconds(self, obj):
        return obj.average_reading_time()


class AdminContentArticleDetailSerializer(AdminContentArticleListSerializer):
    category_id = serializers.IntegerField(read_only=True)
    tag_ids = serializers.SerializerMethodField()
    share_links = serializers.SerializerMethodField()

    class Meta(AdminContentArticleListSerializer.Meta):
        fields = AdminContentArticleListSerializer.Meta.fields + (
            "content",
            "content_format",
            "category_id",
            "tag_ids",
            "sort_order",
            "seo_title",
            "seo_description",
            "source_url",
            "references_json",
            "offline_at",
            "created_at",
            "share_links",
        )

    def get_tag_ids(self, obj):
        return list(obj.tags.values_list("id", flat=True))

    def get_share_links(self, obj):
        from content.services import ContentArticleService

        return ContentArticleService.generate_share_link(obj)


class AdminContentArticleCreateUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False)
    slug = serializers.CharField(max_length=255, required=False)
    locale = serializers.CharField(max_length=16, required=False, default="zh-CN")
    translation_group_id = serializers.IntegerField(required=False, allow_null=True)
    summary = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    cover_image = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    content = serializers.CharField(required=False)
    content_format = serializers.CharField(required=False, default="markdown")
    category_id = serializers.IntegerField(required=False, allow_null=True)
    tag_ids = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=True)
    status = serializers.ChoiceField(choices=ContentArticle.Status.choices, required=False)
    visibility = serializers.ChoiceField(choices=ContentArticle.Visibility.choices, required=False, default=ContentArticle.Visibility.PUBLIC)
    is_top = serializers.BooleanField(required=False, default=False)
    is_recommended = serializers.BooleanField(required=False, default=False)
    sort_order = serializers.IntegerField(required=False, default=0)
    seo_title = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    seo_description = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    source_url = serializers.CharField(required=False, allow_blank=True, default="")
    references_json = serializers.JSONField(required=False, allow_null=True)

    def validate_references_json(self, value):
        if value in (None, "", [], {}):
            return None
        from content.services import ContentArticleService

        normalized = ContentArticleService.normalize_references_json(value)
        return normalized or None

    def validate(self, attrs):
        instance = self.context.get("instance")
        required = ("title", "content")
        if instance is None:
            missing = [field for field in required if not str(attrs.get(field, "")).strip()]
            if missing:
                raise serializers.ValidationError({field: "required" for field in missing})
        locale = attrs.get("locale", getattr(instance, "locale", "zh-CN"))
        if locale and not LOCALE_RE.match(locale):
            raise serializers.ValidationError({"locale": "invalid_locale"})
        content_format = attrs.get("content_format", getattr(instance, "content_format", "markdown"))
        if content_format != "markdown":
            raise serializers.ValidationError({"content_format": "markdown_only"})
        category_id = attrs.get("category_id")
        if category_id is not None and not ContentCategory.objects.filter(id=category_id, is_active=True).exists():
            raise serializers.ValidationError({"category_id": "not_found_or_inactive"})
        tag_ids = attrs.get("tag_ids")
        if tag_ids is not None:
            found = set(ContentTag.objects.filter(id__in=tag_ids, is_active=True).values_list("id", flat=True))
            missing = set(tag_ids) - found
            if missing:
                raise serializers.ValidationError({"tag_ids": f"not_found_or_inactive:{sorted(missing)}"})
        return attrs


class AdminContentArticleActionSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class AdminContentArticlePublishSerializer(AdminContentArticleActionSerializer):
    published_at = serializers.DateTimeField(required=False, allow_null=True)


class AdminContentTagMergeSerializer(serializers.Serializer):
    source_tag_id = serializers.IntegerField()
    target_tag_id = serializers.IntegerField()

    def validate(self, attrs):
        if attrs["source_tag_id"] == attrs["target_tag_id"]:
            raise serializers.ValidationError({"target_tag_id": "same_as_source"})
        return attrs


class AdminContentArticleVersionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = ContentArticleVersion
        fields = (
            "id",
            "article",
            "version_no",
            "title",
            "summary",
            "content",
            "content_format",
            "metadata_json",
            "change_note",
            "created_by",
            "created_by_name",
            "created_at",
        )


class PublicContentArticleListSerializer(serializers.ModelSerializer):
    category = ContentArticleCategoryBriefSerializer(read_only=True)
    tags = ContentArticleTagBriefSerializer(many=True, read_only=True)
    estimated_reading_minutes = serializers.SerializerMethodField()

    class Meta:
        model = ContentArticle
        fields = ("id", "title", "slug", "locale", "summary", "cover_image", "category", "tags", "published_at", "estimated_reading_minutes")

    def get_estimated_reading_minutes(self, obj):
        words = len((obj.content or "").strip())
        return max(1, int(words / 500) + (1 if words % 500 else 0))


class PublicContentArticleDetailSerializer(PublicContentArticleListSerializer):
    references_json = serializers.SerializerMethodField()
    references = serializers.SerializerMethodField()
    share_links = serializers.SerializerMethodField()
    share_url = serializers.SerializerMethodField()

    class Meta(PublicContentArticleListSerializer.Meta):
        fields = PublicContentArticleListSerializer.Meta.fields + (
            "content",
            "content_format",
            "source_url",
            "references_json",
            "references",
            "seo_title",
            "seo_description",
            "share_links",
            "share_url",
        )

    def get_references_json(self, obj):
        from content.services import ContentArticleService

        return ContentArticleService.normalize_references_json(obj.references_json)

    def get_references(self, obj):
        return self.get_references_json(obj)

    def get_share_links(self, obj):
        from content.services import ContentArticleService

        return ContentArticleService.generate_share_link(obj)

    def get_share_url(self, obj):
        return self.get_share_links(obj).get("share_url", "")


class PublicContentReadEventSerializer(serializers.Serializer):
    locale = serializers.CharField(required=False, allow_blank=True, max_length=16)
    session_id = serializers.CharField(required=False, allow_blank=True, max_length=64)
    client_platform = serializers.CharField(required=False, allow_blank=True, max_length=32)


class PublicContentReadingDurationSerializer(PublicContentReadEventSerializer):
    duration_seconds = serializers.IntegerField(min_value=1)
