from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator
from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from backoffice.audit import write_audit_log
from common.http_cache import build_etag, etag_matches
from common.permissions import AdminCodePermission, AdminOnlyPermission
from common.response import error_response, success_response
from content.models import ContentArticle, ContentArticleVersion, ContentCategory, ContentTag
from content.serializers import (
    AdminContentArticleActionSerializer,
    AdminContentArticleCreateUpdateSerializer,
    AdminContentArticleDetailSerializer,
    AdminContentArticleListSerializer,
    AdminContentArticlePublishSerializer,
    AdminContentArticleVersionSerializer,
    AdminContentTagMergeSerializer,
    ContentCategorySerializer,
    ContentTagSerializer,
    PublicContentArticleDetailSerializer,
    PublicContentArticleListSerializer,
    PublicContentReadingDurationSerializer,
    PublicContentReadEventSerializer,
)
from content.services import (
    ContentArticleService,
    ContentCategoryService,
    ContentReadStatService,
    ContentTagService,
    build_pagination,
    parse_bool,
)


def page_params(request):
    page = max(int(request.query_params.get("page", "1") or "1"), 1)
    page_size = min(max(int(request.query_params.get("page_size", "20") or "20"), 1), 100)
    return page, page_size


def validation_error_response(exc):
    detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or str(exc)
    return error_response(msg=detail, code=40001, status_code=status.HTTP_400_BAD_REQUEST)


def public_cache_max_age(request) -> int:
    default_max_age = max(int(getattr(settings, "CONTENT_PUBLIC_CACHE_MAX_AGE", 86400)), 0)
    raw = request.headers.get("X-Cache-Max-Age") or request.query_params.get("cache_max_age")
    if raw in (None, ""):
        return default_max_age
    try:
        requested = int(raw)
    except (TypeError, ValueError):
        return default_max_age
    return min(max(requested, 0), default_max_age)


def public_cached_success_response(request, data, msg: str = "success"):
    # 客户端科普页 GET 接口使用 ETag 协商缓存，命中时返回 304 空响应。
    payload = {"code": 0, "msg": msg, "data": data}
    etag = build_etag(payload)
    if etag_matches(request.headers.get("If-None-Match"), etag):
        response = HttpResponse(status=status.HTTP_304_NOT_MODIFIED)
    else:
        response = success_response(data, msg=msg)
    response["ETag"] = etag
    response["Cache-Control"] = f"public, max-age={public_cache_max_age(request)}, must-revalidate"
    return response


class AdminContentOverviewView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        data = ContentArticleService.overview()
        data["popular_articles"] = AdminContentArticleListSerializer(data["popular_articles"], many=True).data
        data["recent_articles"] = AdminContentArticleListSerializer(data["recent_articles"], many=True).data
        return success_response(data)


class AdminContentArticleSqlExportView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        params = request.query_params
        sql = ContentArticleService.build_export_sql(
            since=params.get("since") or None,
            until=params.get("until") or None,
            locale=params.get("locale") or None,
            status_val=params.get("status"),
        )
        ts = timezone.now().strftime("%Y%m%d_%H%M%S")
        filename = f"articles_{ts}.sql"
        response = HttpResponse(sql, content_type="application/sql; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class AdminContentArticleListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = ContentArticleService.list_admin_articles(request.query_params)
        deleted = parse_bool(request.query_params.get("deleted"))
        if deleted is True:
            queryset = ContentArticle.objects.filter(deleted_at__isnull=False).select_related("category", "author", "last_editor").prefetch_related("tags").order_by("-deleted_at", "-id")
        page, page_size = page_params(request)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        payload = {
            "items": AdminContentArticleListSerializer(page_obj.object_list, many=True).data,
            "pagination": build_pagination(page_obj, page_size),
        }
        return success_response(payload)

    def post(self, request):
        if not request.user.is_superuser:
            from backoffice.rbac import has_permission_code

            if not has_permission_code(request.user.id, "content.article.create"):
                return error_response(msg="permission_denied", code=40301, status_code=status.HTTP_403_FORBIDDEN)
        serializer = AdminContentArticleCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        article = ContentArticleService.create_article(request.user, dict(serializer.validated_data))
        payload = AdminContentArticleDetailSerializer(article).data
        write_audit_log(request, action="content.article.create", resource_type="content_article", resource_id=str(article.id), status_code=201, response_payload=payload)
        return success_response(payload, msg="created", status_code=status.HTTP_201_CREATED)


class AdminContentArticleDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get_object(self, article_id):
        return get_object_or_404(ContentArticle.objects.select_related("category", "author", "last_editor").prefetch_related("tags"), id=article_id)

    def get(self, request, article_id: int):
        return success_response(AdminContentArticleDetailSerializer(self.get_object(article_id)).data)

    def patch(self, request, article_id: int):
        article = self.get_object(article_id)
        serializer = AdminContentArticleCreateUpdateSerializer(data=request.data, partial=True, context={"instance": article})
        serializer.is_valid(raise_exception=True)
        article = ContentArticleService.update_article(request.user, article, dict(serializer.validated_data))
        payload = AdminContentArticleDetailSerializer(article).data
        write_audit_log(request, action="content.article.update", resource_type="content_article", resource_id=str(article.id), response_payload=payload)
        return success_response(payload, msg="updated")

    def delete(self, request, article_id: int):
        article = self.get_object(article_id)
        serializer = AdminContentArticleActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        ContentArticleService.soft_delete_article(request.user, article, comment=serializer.validated_data.get("comment", ""), request=request)
        return success_response({"success": True}, msg="deleted")


class AdminContentArticlePublishView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "content.article.publish"

    def post(self, request, article_id: int):
        article = get_object_or_404(ContentArticle, id=article_id, deleted_at__isnull=True)
        serializer = AdminContentArticlePublishSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            version = ContentArticleService.publish_article(
                request.user,
                article,
                published_at=serializer.validated_data.get("published_at"),
                comment=serializer.validated_data.get("comment", ""),
                request=request,
            )
        except DjangoValidationError as exc:
            return validation_error_response(exc)
        return success_response(
            {
                "article": AdminContentArticleDetailSerializer(article).data,
                "version": AdminContentArticleVersionSerializer(version).data,
            },
            msg="published",
        )


class AdminContentArticleOfflineView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "content.article.offline"

    def post(self, request, article_id: int):
        article = get_object_or_404(ContentArticle, id=article_id, deleted_at__isnull=True)
        serializer = AdminContentArticleActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        article = ContentArticleService.offline_article(request.user, article, comment=serializer.validated_data.get("comment", ""), request=request)
        return success_response(AdminContentArticleDetailSerializer(article).data, msg="offline")


class AdminContentArticleArchiveView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "content.article.archive"

    def post(self, request, article_id: int):
        article = get_object_or_404(ContentArticle, id=article_id, deleted_at__isnull=True)
        serializer = AdminContentArticleActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        article = ContentArticleService.archive_article(request.user, article, comment=serializer.validated_data.get("comment", ""), request=request)
        return success_response(AdminContentArticleDetailSerializer(article).data, msg="archived")


class AdminContentArticleRestoreView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "content.article.delete"

    def post(self, request, article_id: int):
        article = get_object_or_404(ContentArticle, id=article_id, deleted_at__isnull=False)
        serializer = AdminContentArticleActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        article = ContentArticleService.restore_article(request.user, article, comment=serializer.validated_data.get("comment", ""), request=request)
        return success_response(AdminContentArticleDetailSerializer(article).data, msg="restored")


class AdminContentArticlePreviewView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, article_id: int):
        article = get_object_or_404(ContentArticle, id=article_id)
        payload = AdminContentArticleDetailSerializer(article).data
        payload["markdown"] = article.content
        return success_response(payload)


class AdminContentArticleShareLinkView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, article_id: int):
        article = get_object_or_404(ContentArticle, id=article_id)
        links = ContentArticleService.generate_share_link(article)
        links.update({"title": article.title, "summary": article.summary, "cover_image": article.cover_image})
        return success_response(links)


class AdminContentArticleVersionListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, article_id: int):
        article = get_object_or_404(ContentArticle, id=article_id)
        versions = article.versions.select_related("created_by").all()
        return success_response({"items": AdminContentArticleVersionSerializer(versions, many=True).data})


class AdminContentArticleRollbackView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "content.version.rollback"

    def post(self, request, article_id: int, version_id: int):
        article = get_object_or_404(ContentArticle, id=article_id, deleted_at__isnull=True)
        version = get_object_or_404(ContentArticleVersion, id=version_id, article=article)
        serializer = AdminContentArticleActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        article = ContentArticleService.rollback_article(request.user, article, version, comment=serializer.validated_data.get("comment", ""), request=request)
        return success_response(AdminContentArticleDetailSerializer(article).data, msg="rolled_back")


class AdminContentCategoryListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        tree = parse_bool(request.query_params.get("tree"))
        include_inactive = parse_bool(request.query_params.get("include_inactive")) is True
        if tree is not False:
            return success_response(ContentCategoryService.list_tree(include_inactive=include_inactive))
        queryset = ContentCategory.objects.all().order_by("sort_order", "id")
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        return success_response(ContentCategorySerializer(queryset, many=True).data)

    def post(self, request):
        serializer = ContentCategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ContentCategoryService.validate_parent(None, serializer.validated_data.get("parent_id") or 0)
        except DjangoValidationError as exc:
            return validation_error_response(exc)
        category = serializer.save()
        write_audit_log(request, action="content.category.create", resource_type="content_category", resource_id=str(category.id), status_code=201)
        return success_response(ContentCategorySerializer(category).data, msg="created", status_code=status.HTTP_201_CREATED)


class AdminContentCategoryDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def patch(self, request, category_id: int):
        category = get_object_or_404(ContentCategory, id=category_id)
        serializer = ContentCategorySerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            ContentCategoryService.validate_parent(category.id, serializer.validated_data.get("parent_id", category.parent_id))
        except DjangoValidationError as exc:
            return validation_error_response(exc)
        category = serializer.save()
        write_audit_log(request, action="content.category.update", resource_type="content_category", resource_id=str(category.id))
        return success_response(ContentCategorySerializer(category).data, msg="updated")

    def delete(self, request, category_id: int):
        category = get_object_or_404(ContentCategory, id=category_id)
        result = ContentCategoryService.delete_or_disable(category)
        write_audit_log(request, action="content.category.delete", resource_type="content_category", resource_id=str(category_id))
        return success_response(ContentCategorySerializer(result).data if result else {"deleted": True}, msg="deleted" if result is None else "disabled")


class AdminContentTagListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = ContentTagService.list_tags(request.query_params)
        page, page_size = page_params(request)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        return success_response({"items": ContentTagSerializer(page_obj.object_list, many=True).data, "pagination": build_pagination(page_obj, page_size)})

    def post(self, request):
        serializer = ContentTagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tag = serializer.save()
        write_audit_log(request, action="content.tag.create", resource_type="content_tag", resource_id=str(tag.id), status_code=201)
        return success_response(ContentTagSerializer(tag).data, msg="created", status_code=status.HTTP_201_CREATED)


class AdminContentTagDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def patch(self, request, tag_id: int):
        tag = get_object_or_404(ContentTag, id=tag_id)
        serializer = ContentTagSerializer(tag, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        tag = serializer.save()
        write_audit_log(request, action="content.tag.update", resource_type="content_tag", resource_id=str(tag.id))
        return success_response(ContentTagSerializer(tag).data, msg="updated")

    def delete(self, request, tag_id: int):
        tag = get_object_or_404(ContentTag, id=tag_id)
        result = ContentTagService.delete_or_disable(tag)
        write_audit_log(request, action="content.tag.delete", resource_type="content_tag", resource_id=str(tag_id))
        return success_response(ContentTagSerializer(result).data if result else {"deleted": True}, msg="deleted" if result is None else "disabled")


class AdminContentTagMergeView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "content.tag.merge"

    def post(self, request):
        serializer = AdminContentTagMergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source = get_object_or_404(ContentTag, id=serializer.validated_data["source_tag_id"])
        target = get_object_or_404(ContentTag, id=serializer.validated_data["target_tag_id"])
        try:
            moved = ContentTagService.merge_tags(source, target)
        except DjangoValidationError as exc:
            return validation_error_response(exc)
        write_audit_log(request, action="content.tag.merge", resource_type="content_tag", resource_id=str(target.id), response_payload={"source_tag_id": source.id, "target_tag_id": target.id})
        return success_response({"source_tag_id": source.id, "target_tag_id": target.id, "moved_article_count": moved}, msg="merged")


class AdminContentAnalyticsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        articles = ContentArticle.objects.filter(deleted_at__isnull=True).order_by("-view_count")[:20]
        return success_response({"items": AdminContentArticleListSerializer(articles, many=True).data})


class AdminContentComplianceView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = ContentArticle.objects.filter(deleted_at__isnull=True).filter(Q(source_url="") & (Q(references_json__isnull=True) | Q(references_json=[]))).select_related("category").prefetch_related("tags")
        page, page_size = page_params(request)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        return success_response({"items": AdminContentArticleListSerializer(page_obj.object_list, many=True).data, "pagination": build_pagination(page_obj, page_size)})


class PublicContentArticleListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        queryset = ContentArticleService.list_public_articles(request.query_params)
        page, page_size = page_params(request)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        payload = {"items": PublicContentArticleListSerializer(page_obj.object_list, many=True).data, "pagination": build_pagination(page_obj, page_size)}
        return public_cached_success_response(request, payload)


class PublicContentArticleDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug: str):
        try:
            article = ContentArticleService.get_public_article_by_slug(slug, request.query_params.get("locale") or "zh-CN")
        except ContentArticle.DoesNotExist:
            return error_response(msg="not_found", code=40401, status_code=status.HTTP_404_NOT_FOUND)
        return public_cached_success_response(request, PublicContentArticleDetailSerializer(article).data)


class PublicContentArticleDetailByIDView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, article_id: int):
        locale = (request.query_params.get("locale") or "").strip() or None
        try:
            article = ContentArticleService.get_public_article_by_id(article_id, locale)
        except ContentArticle.DoesNotExist:
            return error_response(msg="not_found", code=40401, status_code=status.HTTP_404_NOT_FOUND)
        return public_cached_success_response(request, PublicContentArticleDetailSerializer(article).data)


class PublicContentCategoryListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return public_cached_success_response(request, ContentCategoryService.list_tree(include_inactive=False))


class PublicContentTagListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        locale = request.query_params.get("locale") or "zh-CN"
        return public_cached_success_response(request, ContentTagSerializer(ContentTagService.list_public_tags(locale), many=True).data)


class PublicContentArticleViewEventView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, article_id: int):
        article = get_object_or_404(ContentArticle, id=article_id, deleted_at__isnull=True, status=ContentArticle.Status.PUBLISHED)
        serializer = PublicContentReadEventSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        ContentReadStatService.record_view(
            article,
            request.user,
            locale=serializer.validated_data.get("locale") or article.locale,
            session_id=serializer.validated_data.get("session_id", ""),
            client_platform=serializer.validated_data.get("client_platform", ""),
        )
        return success_response({"success": True})


class PublicContentArticleReadingDurationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, article_id: int):
        article = get_object_or_404(ContentArticle, id=article_id, deleted_at__isnull=True, status=ContentArticle.Status.PUBLISHED)
        serializer = PublicContentReadingDurationSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        seconds = ContentReadStatService.record_duration(
            article,
            request.user,
            duration_seconds=serializer.validated_data["duration_seconds"],
            locale=serializer.validated_data.get("locale") or article.locale,
            session_id=serializer.validated_data.get("session_id", ""),
            client_platform=serializer.validated_data.get("client_platform", ""),
        )
        return success_response({"success": True, "accepted_duration_seconds": seconds})


class PublicContentArticleShareLinkView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, article_id: int):
        article = get_object_or_404(ContentArticle, id=article_id, deleted_at__isnull=True, status=ContentArticle.Status.PUBLISHED)
        payload = ContentArticleService.generate_share_link(article)
        payload.update({"title": article.title, "summary": article.summary, "cover_image": article.cover_image})
        return public_cached_success_response(request, payload)
