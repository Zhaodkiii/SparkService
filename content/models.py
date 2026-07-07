from django.conf import settings
from django.db import models
from django.utils import timezone


class ContentCategory(models.Model):
    name = models.CharField("分类名称", max_length=50, unique=True)
    slug = models.CharField("分类别名", max_length=50, unique=True)
    parent_id = models.PositiveIntegerField("父级分类 ID", default=0, db_index=True)
    description = models.CharField("分类说明", max_length=255, blank=True, default="")
    sort_order = models.IntegerField("排序权重", default=0, db_index=True)
    is_active = models.BooleanField("是否启用", default=True, db_index=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "content_categories"
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["parent_id", "sort_order"], name="content_cat_parent_sort_idx"),
            models.Index(fields=["is_active", "sort_order"], name="content_cat_active_sort_idx"),
        ]

    def __str__(self):
        return self.name


class ContentTag(models.Model):
    name = models.CharField("标签名称", max_length=50, unique=True)
    slug = models.CharField("标签别名", max_length=50, unique=True)
    description = models.CharField("标签说明", max_length=255, blank=True, default="")
    article_count = models.PositiveIntegerField("关联文章数量", default=0, db_index=True)
    is_active = models.BooleanField("是否启用", default=True, db_index=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "content_tags"
        ordering = ["name", "id"]
        indexes = [
            models.Index(fields=["is_active", "article_count"], name="content_tag_active_count_idx"),
        ]

    def __str__(self):
        return self.name


class ContentArticle(models.Model):
    class Status(models.IntegerChoices):
        DRAFT = 0, "草稿"
        PUBLISHED = 2, "已发布"
        OFFLINE = 3, "已下架"
        ARCHIVED = 4, "已归档"

    class Visibility(models.IntegerChoices):
        PRIVATE = 0, "私密"
        PUBLIC = 1, "公开"
        UNLISTED = 2, "未列出"

    title = models.CharField("文章标题", max_length=255, db_index=True)
    slug = models.CharField("URL 别名", max_length=255)
    locale = models.CharField("内容语言", max_length=16, default="zh-CN", db_index=True)
    translation_group_id = models.BigIntegerField("多语言翻译组 ID", null=True, blank=True, db_index=True)
    summary = models.CharField("文章摘要", max_length=500, blank=True, default="")
    cover_image = models.CharField("封面图片 URL", max_length=500, blank=True, default="")
    content = models.TextField("Markdown 正文")
    content_format = models.CharField("正文格式", max_length=30, default="markdown", db_index=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="创建人",
        related_name="content_articles",
        on_delete=models.PROTECT,
    )
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="最近编辑人",
        null=True,
        blank=True,
        related_name="edited_content_articles",
        on_delete=models.SET_NULL,
    )
    category = models.ForeignKey(
        ContentCategory,
        verbose_name="主分类",
        null=True,
        blank=True,
        related_name="articles",
        on_delete=models.SET_NULL,
    )
    tags = models.ManyToManyField(ContentTag, through="ContentArticleTag", related_name="articles")
    status = models.PositiveSmallIntegerField("状态", choices=Status.choices, default=Status.DRAFT, db_index=True)
    visibility = models.PositiveSmallIntegerField("可见性", choices=Visibility.choices, default=Visibility.PUBLIC, db_index=True)
    is_top = models.BooleanField("是否置顶", default=False, db_index=True)
    is_recommended = models.BooleanField("是否推荐", default=False, db_index=True)
    sort_order = models.IntegerField("排序权重", default=0, db_index=True)
    view_count = models.PositiveIntegerField("点击量", default=0)
    read_count = models.PositiveIntegerField("有效阅读次数", default=0)
    reading_time_seconds = models.PositiveBigIntegerField("累计阅读时长秒数", default=0)
    seo_title = models.CharField("SEO 标题", max_length=255, blank=True, default="")
    seo_description = models.CharField("SEO 描述", max_length=500, blank=True, default="")
    source_url = models.TextField("来源链接", blank=True, default="")
    references_json = models.JSONField("参考文献", null=True, blank=True)
    published_at = models.DateTimeField("发布时间", null=True, blank=True, db_index=True)
    offline_at = models.DateTimeField("下架时间", null=True, blank=True, db_index=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True, db_index=True)
    deleted_at = models.DateTimeField("软删除时间", null=True, blank=True, db_index=True)

    class Meta:
        db_table = "content_articles"
        ordering = ["-published_at", "-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["locale", "slug"], name="uniq_content_article_locale_slug"),
            models.CheckConstraint(condition=models.Q(content_format="markdown"), name="chk_content_article_markdown"),
        ]
        indexes = [
            models.Index(fields=["category", "locale", "status", "published_at"], name="cont_art_cat_loc_pub_idx"),
            models.Index(fields=["locale", "status", "published_at"], name="content_art_loc_stat_pub_idx"),
            models.Index(fields=["author", "status", "updated_at"], name="content_art_author_status_idx"),
            models.Index(fields=["is_top", "status", "published_at"], name="content_art_top_pub_idx"),
            models.Index(fields=["is_recommended", "status", "published_at"], name="content_art_rec_pub_idx"),
            models.Index(fields=["translation_group_id"], name="content_art_trans_group_idx"),
        ]

    def __str__(self):
        return f"{self.title}({self.locale})"

    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED and self.deleted_at is None

    def can_public_read(self) -> bool:
        return self.is_published() and self.visibility in {self.Visibility.PUBLIC, self.Visibility.UNLISTED}

    def average_reading_time(self) -> int:
        if not self.read_count:
            return 0
        return int(self.reading_time_seconds / self.read_count)

    def mark_deleted(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])


class ContentArticleTag(models.Model):
    article = models.ForeignKey(ContentArticle, related_name="article_tag_links", on_delete=models.CASCADE)
    tag = models.ForeignKey(ContentTag, related_name="article_tag_links", on_delete=models.CASCADE)
    created_at = models.DateTimeField("关联创建时间", auto_now_add=True)

    class Meta:
        db_table = "content_article_tags"
        constraints = [
            models.UniqueConstraint(fields=["article", "tag"], name="uniq_content_article_tag"),
        ]
        indexes = [
            models.Index(fields=["tag"], name="content_article_tag_tag_idx"),
        ]


class ContentArticleVersion(models.Model):
    article = models.ForeignKey(ContentArticle, related_name="versions", on_delete=models.CASCADE)
    version_no = models.PositiveIntegerField("版本号")
    title = models.CharField("快照标题", max_length=255)
    summary = models.CharField("快照摘要", max_length=500, blank=True, default="")
    content = models.TextField("快照正文")
    content_format = models.CharField("快照正文格式", max_length=30)
    metadata_json = models.JSONField("元数据快照", null=True, blank=True)
    change_note = models.CharField("变更说明", max_length=500, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="content_article_versions", on_delete=models.PROTECT)
    created_at = models.DateTimeField("版本创建时间", auto_now_add=True, db_index=True)

    class Meta:
        db_table = "content_article_versions"
        ordering = ["-version_no", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["article", "version_no"], name="uniq_content_article_version_no"),
        ]
        indexes = [
            models.Index(fields=["article", "created_at"], name="cont_ver_article_time_idx"),
            models.Index(fields=["created_by", "created_at"], name="cont_ver_creator_time_idx"),
        ]


class ContentArticleOperationLog(models.Model):
    article = models.ForeignKey(ContentArticle, related_name="operation_logs", on_delete=models.CASCADE)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="content_article_operations", on_delete=models.PROTECT)
    action = models.CharField("操作动作", max_length=32, db_index=True)
    from_status = models.PositiveSmallIntegerField("操作前状态", null=True, blank=True)
    to_status = models.PositiveSmallIntegerField("操作后状态", null=True, blank=True)
    comment = models.CharField("操作原因", max_length=500, blank=True, default="")
    created_at = models.DateTimeField("操作时间", auto_now_add=True, db_index=True)

    class Meta:
        db_table = "content_article_operation_logs"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["article", "created_at"], name="content_op_article_time_idx"),
            models.Index(fields=["operator", "created_at"], name="content_op_operator_time_idx"),
            models.Index(fields=["action", "created_at"], name="content_op_action_time_idx"),
        ]


class ContentArticleReadEvent(models.Model):
    class EventType(models.TextChoices):
        VIEW = "view", "详情点击"
        READ_DURATION = "read_duration", "阅读时长"

    article = models.ForeignKey(ContentArticle, related_name="read_events", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="content_read_events", on_delete=models.SET_NULL)
    locale = models.CharField("阅读语言", max_length=16, db_index=True)
    event_type = models.CharField("事件类型", max_length=32, choices=EventType.choices, db_index=True)
    duration_seconds = models.PositiveIntegerField("阅读时长秒数", default=0)
    session_id = models.CharField("App 会话 ID", max_length=64, blank=True, default="", db_index=True)
    client_platform = models.CharField("客户端平台", max_length=32, blank=True, default="", db_index=True)
    created_at = models.DateTimeField("上报时间", auto_now_add=True, db_index=True)

    class Meta:
        db_table = "content_article_read_events"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["article", "created_at"], name="content_read_article_time_idx"),
            models.Index(fields=["user", "created_at"], name="content_read_user_time_idx"),
            models.Index(fields=["locale", "created_at"], name="content_read_locale_time_idx"),
            models.Index(fields=["event_type", "created_at"], name="content_read_event_time_idx"),
            models.Index(fields=["session_id"], name="content_read_session_idx"),
        ]
