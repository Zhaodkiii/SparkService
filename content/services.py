import json
import re
import secrets
import string
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Count, F, Max, Q, Sum
from django.utils import timezone

from backoffice.audit import write_audit_log
from content.models import (
    ContentArticle,
    ContentArticleOperationLog,
    ContentArticleReadEvent,
    ContentArticleTag,
    ContentArticleVersion,
    ContentCategory,
    ContentTag,
)


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,254}$")
LOCALE_RE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")
ARTICLE_SLUG_ALPHABET = string.ascii_lowercase + string.digits


def parse_bool(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "y"}


def build_pagination(page_obj, page_size: int) -> dict:
    return {
        "page": page_obj.number,
        "page_size": page_size,
        "total": page_obj.paginator.count,
        "total_pages": page_obj.paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
        "previous_page": page_obj.previous_page_number() if page_obj.has_previous() else None,
    }


def _sql_vendor() -> str:
    return connection.vendor


def _sql_quote_identifier(name: str) -> str:
    vendor = _sql_vendor()
    if vendor == "mysql":
        return f"`{name}`"
    return f'"{name}"'


def _sql_escape_str(value) -> str:
    if value is None:
        return "NULL"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _sql_fmt_int(value) -> str:
    if value is None:
        return "NULL"
    return str(int(value))


def _sql_fmt_bool(value) -> str:
    if _sql_vendor() == "mysql":
        return "1" if value else "0"
    return "TRUE" if value else "FALSE"


def _sql_fmt_dt(value) -> str:
    if value is None:
        return "NULL"
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return _sql_escape_str(value.isoformat(sep=" ", timespec="seconds"))


def _sql_fmt_json(value) -> str:
    if value is None:
        return "NULL"
    return _sql_escape_str(json.dumps(value, ensure_ascii=False))


def _sql_insert_prefix(table: str, columns: list[str]) -> str:
    table_name = _sql_quote_identifier(table)
    column_list = ", ".join(_sql_quote_identifier(column) for column in columns)
    if _sql_vendor() == "mysql":
        return f"INSERT IGNORE INTO {table_name} ({column_list}) VALUES "
    return f"INSERT INTO {table_name} ({column_list}) VALUES "


def _sql_insert_suffix() -> str:
    if _sql_vendor() == "postgresql":
        return " ON CONFLICT (id) DO NOTHING;"
    return ";"


def _sql_values_row(values: list[str]) -> str:
    return f"({', '.join(values)})"


def trusted_asset_hosts() -> list[str]:
    raw = getattr(settings, "CONTENT_TRUSTED_ASSET_HOSTS", "")
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return list(raw or [])


class ContentArticleService:
    @staticmethod
    def generate_unique_slug(length: int = 14) -> str:
        # 文章 slug 面向分享 URL，使用 URL-safe 随机码，避免泄露标题语义。
        if length < 12 or length > 16:
            raise ValueError("article_slug_length_must_be_12_to_16")
        for _ in range(32):
            candidate = "".join(secrets.choice(ARTICLE_SLUG_ALPHABET) for _ in range(length))
            # 生成后必须查库确认不重复；这里按全局 slug 去重，跨语言也保持分享链接稳定唯一。
            if not ContentArticle.objects.filter(slug=candidate).exists():
                return candidate
        raise RuntimeError("article_slug_generate_failed")

    @staticmethod
    def list_admin_articles(params):
        queryset = (
            ContentArticle.objects.filter(deleted_at__isnull=True)
            .select_related("category", "author", "last_editor")
            .prefetch_related("tags")
            .order_by("-updated_at", "-id")
        )
        q = (params.get("q") or "").strip()
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(slug__icontains=q))
        for field in ("status", "visibility", "locale", "author_id", "category_id"):
            value = params.get(field)
            if value not in (None, ""):
                queryset = queryset.filter(**{field: value})
        tag_id = params.get("tag_id")
        if tag_id not in (None, ""):
            queryset = queryset.filter(tags__id=tag_id)
        for field in ("is_top", "is_recommended"):
            value = parse_bool(params.get(field))
            if value is not None:
                queryset = queryset.filter(**{field: value})
        published_from = params.get("published_from")
        if published_from:
            queryset = queryset.filter(published_at__gte=published_from)
        published_to = params.get("published_to")
        if published_to:
            queryset = queryset.filter(published_at__lte=published_to)
        return queryset.distinct()

    @staticmethod
    def list_public_articles(params):
        queryset = (
            ContentArticle.objects.filter(
                deleted_at__isnull=True,
                status=ContentArticle.Status.PUBLISHED,
                visibility=ContentArticle.Visibility.PUBLIC,
            )
            .select_related("category")
            .prefetch_related("tags")
            .order_by("sort_order", "-published_at", "-id")
        )
        locale = (params.get("locale") or "zh-CN").strip()
        queryset = queryset.filter(locale=locale)
        q = (params.get("q") or "").strip()
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(summary__icontains=q))
        category_id = params.get("category_id")
        if category_id not in (None, ""):
            queryset = queryset.filter(category_id=category_id)
        tag_id = params.get("tag_id")
        if tag_id not in (None, ""):
            queryset = queryset.filter(tags__id=tag_id)
        recommended = parse_bool(params.get("recommended"))
        if recommended is not None:
            queryset = queryset.filter(is_recommended=recommended)
        return queryset.distinct()

    @staticmethod
    def normalize_references_json(value):
        if value in (None, "", [], {}):
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                import json

                parsed = json.loads(text)
            except (TypeError, ValueError, json.JSONDecodeError):
                return [ContentArticleService._normalize_reference_item(text)]
            return ContentArticleService.normalize_references_json(parsed)
        if isinstance(value, dict):
            return [ContentArticleService._normalize_reference_item(value)]
        if isinstance(value, list):
            items = []
            for entry in value:
                if entry in (None, "", {}, []):
                    continue
                items.append(ContentArticleService._normalize_reference_item(entry))
            return items
        return [ContentArticleService._normalize_reference_item(value)]

    @staticmethod
    def _normalize_reference_item(item):
        if isinstance(item, str):
            text = item.strip()
            return {
                "title": text,
                "url": text if text.lower().startswith(("http://", "https://")) else None,
                "source": None,
                "published_at": None,
            }
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("name") or item.get("url") or "").strip()
            url = str(item.get("url") or "").strip() or None
            if not title and url:
                title = url
            source = item.get("source") or item.get("source_type")
            return {
                "title": title,
                "url": url,
                "source": source,
                "published_at": item.get("published_at"),
            }
        text = str(item).strip()
        return {"title": text, "url": None, "source": None, "published_at": None}

    @staticmethod
    def get_public_article_by_slug(slug: str, locale: str):
        return ContentArticle.objects.select_related("category").prefetch_related("tags").get(
            slug=slug,
            locale=locale or "zh-CN",
            deleted_at__isnull=True,
            status=ContentArticle.Status.PUBLISHED,
            visibility__in=[ContentArticle.Visibility.PUBLIC, ContentArticle.Visibility.UNLISTED],
        )

    @staticmethod
    def get_public_article_by_id(article_id: int, locale: str | None = None):
        filters = {
            "id": article_id,
            "deleted_at__isnull": True,
            "status": ContentArticle.Status.PUBLISHED,
            "visibility__in": [ContentArticle.Visibility.PUBLIC, ContentArticle.Visibility.UNLISTED],
        }
        if locale:
            filters["locale"] = locale
        return ContentArticle.objects.select_related("category").prefetch_related("tags").get(**filters)

    @staticmethod
    @transaction.atomic
    def create_article(user, data: dict) -> ContentArticle:
        tag_ids = data.pop("tag_ids", [])
        data.pop("slug", None)
        data["slug"] = ContentArticleService.generate_unique_slug()
        article = ContentArticle.objects.create(author=user, last_editor=user, **data)
        if not article.translation_group_id:
            article.translation_group_id = article.id
            article.save(update_fields=["translation_group_id", "updated_at"])
        ContentArticleService.set_article_tags(article, tag_ids)
        return article

    @staticmethod
    @transaction.atomic
    def update_article(user, article: ContentArticle, data: dict) -> ContentArticle:
        tag_ids = data.pop("tag_ids", None)
        data.pop("slug", None)
        for key, value in data.items():
            setattr(article, key, value)
        article.last_editor = user
        article.save()
        if tag_ids is not None:
            ContentArticleService.set_article_tags(article, tag_ids)
        return article

    @staticmethod
    def set_article_tags(article: ContentArticle, tag_ids: list[int]) -> None:
        old_tag_ids = set(article.tags.values_list("id", flat=True))
        article.tags.set(ContentTag.objects.filter(id__in=tag_ids))
        changed_tag_ids = old_tag_ids.union(set(tag_ids))
        ContentTagService.refresh_article_counts(changed_tag_ids)

    @staticmethod
    def validate_publishable(article: ContentArticle) -> None:
        errors = {}
        if not article.title.strip():
            errors["title"] = "required"
        if not article.slug.strip():
            errors["slug"] = "required"
        if not SLUG_RE.match(article.slug):
            errors["slug"] = "invalid"
        if not LOCALE_RE.match(article.locale):
            errors["locale"] = "invalid"
        if not article.content.strip():
            errors["content"] = "required"
        if article.content_format != "markdown":
            errors["content_format"] = "markdown_only"
        duplicate = ContentArticle.objects.filter(locale=article.locale, slug=article.slug, deleted_at__isnull=True).exclude(id=article.id).exists()
        if duplicate:
            errors["slug"] = "duplicate"
        if not article.source_url.strip() and not ContentArticleService.normalize_references_json(article.references_json):
            errors["references"] = "medical_reference_required"
        asset_hosts = trusted_asset_hosts()
        if asset_hosts:
            bad_urls = []
            for url in MARKDOWN_IMAGE_RE.findall(article.content or ""):
                if url.startswith("http") and not any(host in url for host in asset_hosts):
                    bad_urls.append(url)
            if bad_urls:
                errors["content_images"] = "untrusted_image_host"
        if errors:
            raise ValidationError(errors)

    @staticmethod
    @transaction.atomic
    def publish_article(user, article: ContentArticle, *, published_at=None, comment: str = "", request=None):
        ContentArticleService.validate_publishable(article)
        old_status = article.status
        article.status = ContentArticle.Status.PUBLISHED
        article.published_at = published_at or timezone.now()
        article.offline_at = None
        article.last_editor = user
        article.save(update_fields=["status", "published_at", "offline_at", "last_editor", "updated_at"])
        version = ContentArticleVersionService.create_from_article(article, user, comment)
        ContentArticleOperationLog.objects.create(
            article=article,
            operator=user,
            action="publish",
            from_status=old_status,
            to_status=article.status,
            comment=comment,
        )
        if request is not None:
            write_audit_log(request, action="content.article.publish", resource_type="content_article", resource_id=str(article.id))
        return version

    @staticmethod
    @transaction.atomic
    def offline_article(user, article: ContentArticle, *, comment: str = "", request=None):
        old_status = article.status
        article.status = ContentArticle.Status.OFFLINE
        article.offline_at = timezone.now()
        article.last_editor = user
        article.save(update_fields=["status", "offline_at", "last_editor", "updated_at"])
        ContentArticleOperationLog.objects.create(article=article, operator=user, action="offline", from_status=old_status, to_status=article.status, comment=comment)
        if request is not None:
            write_audit_log(request, action="content.article.offline", resource_type="content_article", resource_id=str(article.id))
        return article

    @staticmethod
    @transaction.atomic
    def archive_article(user, article: ContentArticle, *, comment: str = "", request=None):
        old_status = article.status
        article.status = ContentArticle.Status.ARCHIVED
        article.last_editor = user
        article.save(update_fields=["status", "last_editor", "updated_at"])
        ContentArticleOperationLog.objects.create(article=article, operator=user, action="archive", from_status=old_status, to_status=article.status, comment=comment)
        if request is not None:
            write_audit_log(request, action="content.article.archive", resource_type="content_article", resource_id=str(article.id))
        return article

    @staticmethod
    @transaction.atomic
    def soft_delete_article(user, article: ContentArticle, *, comment: str = "", request=None):
        old_status = article.status
        article.deleted_at = timezone.now()
        article.last_editor = user
        article.save(update_fields=["deleted_at", "last_editor", "updated_at"])
        ContentArticleOperationLog.objects.create(article=article, operator=user, action="delete", from_status=old_status, to_status=old_status, comment=comment)
        ContentTagService.refresh_article_counts(article.tags.values_list("id", flat=True))
        if request is not None:
            write_audit_log(request, action="content.article.delete", resource_type="content_article", resource_id=str(article.id))

    @staticmethod
    @transaction.atomic
    def restore_article(user, article: ContentArticle, *, comment: str = "", request=None):
        article.deleted_at = None
        article.status = ContentArticle.Status.DRAFT
        article.last_editor = user
        article.save(update_fields=["deleted_at", "status", "last_editor", "updated_at"])
        ContentArticleOperationLog.objects.create(article=article, operator=user, action="restore", from_status=None, to_status=article.status, comment=comment)
        ContentTagService.refresh_article_counts(article.tags.values_list("id", flat=True))
        if request is not None:
            write_audit_log(request, action="content.article.restore", resource_type="content_article", resource_id=str(article.id))
        return article

    @staticmethod
    @transaction.atomic
    def rollback_article(user, article: ContentArticle, version: ContentArticleVersion, *, comment: str = "", request=None):
        old_status = article.status
        article.title = version.title
        article.summary = version.summary
        article.content = version.content
        article.content_format = version.content_format
        metadata = version.metadata_json or {}
        for field in ("slug", "locale", "translation_group_id", "cover_image", "category_id", "visibility", "is_top", "is_recommended", "sort_order", "seo_title", "seo_description", "source_url", "references_json"):
            if field in metadata:
                setattr(article, field, metadata[field])
        article.status = ContentArticle.Status.DRAFT
        article.last_editor = user
        article.save()
        if "tag_ids" in metadata:
            ContentArticleService.set_article_tags(article, metadata["tag_ids"])
        ContentArticleOperationLog.objects.create(article=article, operator=user, action="rollback", from_status=old_status, to_status=article.status, comment=comment)
        if request is not None:
            write_audit_log(request, action="content.version.rollback", resource_type="content_article", resource_id=str(article.id))
        return article

    @staticmethod
    def generate_share_link(article: ContentArticle) -> dict:
        base = getattr(settings, "CONTENT_SHARE_WEB_BASE_URL", "").strip() or getattr(settings, "MEDICAL_SHARE_WEB_BASE_URL", "").strip()
        query = urlencode({"locale": article.locale})
        path = f"/content/{article.slug}?{query}"
        share_url = f"{base.rstrip('/')}{path}" if base else path
        app_scheme_url = f"spark://content/articles/{article.slug}?{query}"
        universal_link_url = share_url
        return {
            "share_url": share_url,
            "app_scheme_url": app_scheme_url,
            "universal_link_url": universal_link_url,
        }

    @staticmethod
    def build_export_sql(*, since=None, until=None, locale=None, status_val=None) -> str:
        queryset = (
            ContentArticle.objects.filter(deleted_at__isnull=True)
            .select_related("category")
            .prefetch_related("tags", "article_tag_links")
            .order_by("id")
        )
        if status_val not in (None, ""):
            queryset = queryset.filter(status=int(status_val))
        else:
            queryset = queryset.filter(status=ContentArticle.Status.PUBLISHED)
        if locale:
            queryset = queryset.filter(locale=locale.strip())
        if since:
            queryset = queryset.filter(published_at__gte=since)
        if until:
            queryset = queryset.filter(published_at__lte=until)

        articles = list(queryset)
        category_ids = {article.category_id for article in articles if article.category_id}
        tag_ids: set[int] = set()
        for article in articles:
            tag_ids.update(article.tags.values_list("id", flat=True))

        categories = list(ContentCategory.objects.filter(id__in=category_ids).order_by("id"))
        tags = list(ContentTag.objects.filter(id__in=tag_ids).order_by("id"))
        article_ids = [article.id for article in articles]
        article_tags = list(ContentArticleTag.objects.filter(article_id__in=article_ids).order_by("id"))

        lines: list[str] = [
            "-- SparkService Article SQL Export",
            f"-- Generated: {timezone.now().isoformat(sep=' ', timespec='seconds')}",
            f"-- Articles: {len(articles)}  Categories: {len(categories)}  Tags: {len(tags)}  ArticleTags: {len(article_tags)}",
            "-- NOTE: author_id / last_editor_id reference accounts_user.id",
            "--       Ensure those user rows exist on the target database first.",
            "",
            "BEGIN;",
            "",
        ]

        category_columns = [
            "id",
            "name",
            "slug",
            "parent_id",
            "description",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        lines.append(f"-- content_categories ({len(categories)} rows)")
        if categories:
            prefix = _sql_insert_prefix("content_categories", category_columns)
            for category in categories:
                values = _sql_values_row(
                    [
                        _sql_fmt_int(category.id),
                        _sql_escape_str(category.name),
                        _sql_escape_str(category.slug),
                        _sql_fmt_int(category.parent_id),
                        _sql_escape_str(category.description),
                        _sql_fmt_int(category.sort_order),
                        _sql_fmt_bool(category.is_active),
                        _sql_fmt_dt(category.created_at),
                        _sql_fmt_dt(category.updated_at),
                    ]
                )
                lines.append(f"{prefix}{values}{_sql_insert_suffix()}")
        lines.append("")

        tag_columns = [
            "id",
            "name",
            "slug",
            "description",
            "article_count",
            "is_active",
            "created_at",
            "updated_at",
        ]
        lines.append(f"-- content_tags ({len(tags)} rows)")
        if tags:
            prefix = _sql_insert_prefix("content_tags", tag_columns)
            for tag in tags:
                values = _sql_values_row(
                    [
                        _sql_fmt_int(tag.id),
                        _sql_escape_str(tag.name),
                        _sql_escape_str(tag.slug),
                        _sql_escape_str(tag.description),
                        _sql_fmt_int(tag.article_count),
                        _sql_fmt_bool(tag.is_active),
                        _sql_fmt_dt(tag.created_at),
                        _sql_fmt_dt(tag.updated_at),
                    ]
                )
                lines.append(f"{prefix}{values}{_sql_insert_suffix()}")
        lines.append("")

        article_columns = [
            "id",
            "title",
            "slug",
            "locale",
            "translation_group_id",
            "summary",
            "cover_image",
            "content",
            "content_format",
            "author_id",
            "last_editor_id",
            "category_id",
            "status",
            "visibility",
            "is_top",
            "is_recommended",
            "sort_order",
            "view_count",
            "read_count",
            "reading_time_seconds",
            "seo_title",
            "seo_description",
            "source_url",
            "references_json",
            "published_at",
            "offline_at",
            "created_at",
            "updated_at",
            "deleted_at",
        ]
        lines.append(f"-- content_articles ({len(articles)} rows)")
        if articles:
            prefix = _sql_insert_prefix("content_articles", article_columns)
            for article in articles:
                values = _sql_values_row(
                    [
                        _sql_fmt_int(article.id),
                        _sql_escape_str(article.title),
                        _sql_escape_str(article.slug),
                        _sql_escape_str(article.locale),
                        _sql_fmt_int(article.translation_group_id),
                        _sql_escape_str(article.summary),
                        _sql_escape_str(article.cover_image),
                        _sql_escape_str(article.content),
                        _sql_escape_str(article.content_format),
                        _sql_fmt_int(article.author_id),
                        _sql_fmt_int(article.last_editor_id),
                        _sql_fmt_int(article.category_id),
                        _sql_fmt_int(article.status),
                        _sql_fmt_int(article.visibility),
                        _sql_fmt_bool(article.is_top),
                        _sql_fmt_bool(article.is_recommended),
                        _sql_fmt_int(article.sort_order),
                        _sql_fmt_int(article.view_count),
                        _sql_fmt_int(article.read_count),
                        _sql_fmt_int(article.reading_time_seconds),
                        _sql_escape_str(article.seo_title),
                        _sql_escape_str(article.seo_description),
                        _sql_escape_str(article.source_url),
                        _sql_fmt_json(article.references_json),
                        _sql_fmt_dt(article.published_at),
                        _sql_fmt_dt(article.offline_at),
                        _sql_fmt_dt(article.created_at),
                        _sql_fmt_dt(article.updated_at),
                        _sql_fmt_dt(article.deleted_at),
                    ]
                )
                lines.append(f"{prefix}{values}{_sql_insert_suffix()}")
        lines.append("")

        article_tag_columns = ["id", "article_id", "tag_id", "created_at"]
        lines.append(f"-- content_article_tags ({len(article_tags)} rows)")
        if article_tags:
            prefix = _sql_insert_prefix("content_article_tags", article_tag_columns)
            for link in article_tags:
                values = _sql_values_row(
                    [
                        _sql_fmt_int(link.id),
                        _sql_fmt_int(link.article_id),
                        _sql_fmt_int(link.tag_id),
                        _sql_fmt_dt(link.created_at),
                    ]
                )
                lines.append(f"{prefix}{values}{_sql_insert_suffix()}")
        lines.append("")
        lines.append("COMMIT;")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def overview() -> dict:
        alive = ContentArticle.objects.filter(deleted_at__isnull=True)
        seven_days_ago = timezone.now() - timedelta(days=7)
        aggregate = alive.aggregate(
            total=Count("id"),
            published=Count("id", filter=Q(status=ContentArticle.Status.PUBLISHED)),
            draft=Count("id", filter=Q(status=ContentArticle.Status.DRAFT)),
            offline=Count("id", filter=Q(status=ContentArticle.Status.OFFLINE)),
            archived=Count("id", filter=Q(status=ContentArticle.Status.ARCHIVED)),
            total_views=Sum("view_count"),
            total_read_seconds=Sum("reading_time_seconds"),
        )
        missing_reference = alive.filter(Q(source_url="") & (Q(references_json__isnull=True) | Q(references_json=[]))).count()
        stale = alive.filter(updated_at__lt=timezone.now() - timedelta(days=180)).count()
        recent_views = ContentArticleReadEvent.objects.filter(event_type=ContentArticleReadEvent.EventType.VIEW, created_at__gte=seven_days_ago).count()
        popular = alive.filter(status=ContentArticle.Status.PUBLISHED).order_by("-view_count", "-published_at")[:10]
        recent = alive.filter(status=ContentArticle.Status.PUBLISHED).order_by("-published_at", "-id")[:10]
        return {
            **{key: value or 0 for key, value in aggregate.items()},
            "missing_reference": missing_reference,
            "stale_review": stale,
            "recent_7d_views": recent_views,
            "popular_articles": popular,
            "recent_articles": recent,
        }


class ContentArticleVersionService:
    @staticmethod
    def create_from_article(article: ContentArticle, user, change_note: str = "") -> ContentArticleVersion:
        last_version = article.versions.aggregate(max_version=Max("version_no")).get("max_version") or 0
        metadata = {
            "slug": article.slug,
            "locale": article.locale,
            "translation_group_id": article.translation_group_id,
            "cover_image": article.cover_image,
            "category_id": article.category_id,
            "tag_ids": list(article.tags.values_list("id", flat=True)),
            "visibility": article.visibility,
            "is_top": article.is_top,
            "is_recommended": article.is_recommended,
            "sort_order": article.sort_order,
            "seo_title": article.seo_title,
            "seo_description": article.seo_description,
            "source_url": article.source_url,
            "references_json": article.references_json,
        }
        return ContentArticleVersion.objects.create(
            article=article,
            version_no=last_version + 1,
            title=article.title,
            summary=article.summary,
            content=article.content,
            content_format=article.content_format,
            metadata_json=metadata,
            change_note=change_note,
            created_by=user,
        )


class ContentCategoryService:
    @staticmethod
    def list_tree(include_inactive: bool = False):
        queryset = ContentCategory.objects.all()
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        rows = list(queryset.order_by("sort_order", "id").values("id", "name", "slug", "parent_id", "description", "sort_order", "is_active"))
        index = {row["id"]: {**row, "children": []} for row in rows}
        roots = []
        for row in index.values():
            parent = index.get(row["parent_id"])
            if parent:
                parent["children"].append(row)
            else:
                roots.append(row)
        return roots

    @staticmethod
    def validate_parent(category_id: int | None, parent_id: int) -> None:
        if not category_id or parent_id == 0:
            return
        if category_id == parent_id:
            raise ValidationError({"parent_id": "cannot_be_self"})
        current = parent_id
        seen = set()
        while current and current not in seen:
            seen.add(current)
            parent = ContentCategory.objects.filter(id=current).first()
            if not parent:
                break
            if parent.parent_id == category_id:
                raise ValidationError({"parent_id": "cannot_use_descendant"})
            current = parent.parent_id

    @staticmethod
    @transaction.atomic
    def delete_or_disable(category: ContentCategory):
        has_children = ContentCategory.objects.filter(parent_id=category.id).exists()
        has_articles = ContentArticle.objects.filter(category=category, deleted_at__isnull=True).exists()
        if has_children or has_articles:
            category.is_active = False
            category.save(update_fields=["is_active", "updated_at"])
            return category
        category.delete()
        return None


class ContentTagService:
    @staticmethod
    def list_tags(params):
        queryset = ContentTag.objects.all().order_by("name", "id")
        q = (params.get("q") or "").strip()
        if q:
            queryset = queryset.filter(Q(name__icontains=q) | Q(slug__icontains=q))
        is_active = parse_bool(params.get("is_active"))
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset

    @staticmethod
    def list_public_tags(locale: str = "zh-CN"):
        return ContentTag.objects.filter(
            is_active=True,
            articles__deleted_at__isnull=True,
            articles__status=ContentArticle.Status.PUBLISHED,
            articles__visibility=ContentArticle.Visibility.PUBLIC,
            articles__locale=locale,
        ).distinct().order_by("name", "id")

    @staticmethod
    def refresh_article_counts(tag_ids):
        for tag_id in set(tag_ids or []):
            count = ContentArticleTag.objects.filter(article__deleted_at__isnull=True, tag_id=tag_id).count()
            ContentTag.objects.filter(id=tag_id).update(article_count=count)

    @staticmethod
    @transaction.atomic
    def delete_or_disable(tag: ContentTag):
        if ContentArticleTag.objects.filter(tag=tag, article__deleted_at__isnull=True).exists():
            tag.is_active = False
            tag.save(update_fields=["is_active", "updated_at"])
            return tag
        tag.delete()
        return None

    @staticmethod
    @transaction.atomic
    def merge_tags(source: ContentTag, target: ContentTag) -> int:
        if source.id == target.id:
            raise ValidationError({"target_tag_id": "same_as_source"})
        article_ids = list(ContentArticleTag.objects.filter(tag=source).values_list("article_id", flat=True))
        moved = 0
        for article_id in article_ids:
            _, created = ContentArticleTag.objects.get_or_create(article_id=article_id, tag=target)
            if created:
                moved += 1
        ContentArticleTag.objects.filter(tag=source).delete()
        source.is_active = False
        source.article_count = 0
        source.save(update_fields=["is_active", "article_count", "updated_at"])
        ContentTagService.refresh_article_counts([target.id])
        return moved


class ContentReadStatService:
    MAX_DURATION_SECONDS = 1800

    @staticmethod
    def normalize_duration(value) -> int:
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            return 0
        if seconds <= 0:
            return 0
        return min(seconds, ContentReadStatService.MAX_DURATION_SECONDS)

    @staticmethod
    @transaction.atomic
    def record_view(article: ContentArticle, user, *, locale: str, session_id: str = "", client_platform: str = ""):
        ContentArticle.objects.filter(id=article.id).update(view_count=F("view_count") + 1)
        ContentArticleReadEvent.objects.create(
            article=article,
            user=user if getattr(user, "is_authenticated", False) else None,
            locale=locale or article.locale,
            event_type=ContentArticleReadEvent.EventType.VIEW,
            session_id=session_id or "",
            client_platform=client_platform or "",
        )

    @staticmethod
    @transaction.atomic
    def record_duration(article: ContentArticle, user, *, duration_seconds: int, locale: str, session_id: str = "", client_platform: str = "") -> int:
        seconds = ContentReadStatService.normalize_duration(duration_seconds)
        if not seconds:
            return 0
        ContentArticle.objects.filter(id=article.id).update(read_count=F("read_count") + 1, reading_time_seconds=F("reading_time_seconds") + seconds)
        ContentArticleReadEvent.objects.create(
            article=article,
            user=user if getattr(user, "is_authenticated", False) else None,
            locale=locale or article.locale,
            event_type=ContentArticleReadEvent.EventType.READ_DURATION,
            duration_seconds=seconds,
            session_id=session_id or "",
            client_platform=client_platform or "",
        )
        return seconds
