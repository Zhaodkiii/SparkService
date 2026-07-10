from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from unittest.mock import patch

from content.models import ContentArticle, ContentCategory, ContentTag
from content.services import ContentArticleService


class ContentArticleServiceTests(TestCase):
    def test_normalize_references_json_from_plain_url(self):
        normalized = ContentArticleService.normalize_references_json("https://example.com/guideline")
        self.assertEqual(
            normalized,
            [{"title": "https://example.com/guideline", "url": "https://example.com/guideline", "source": None, "published_at": None}],
        )

    def test_normalize_references_json_from_object(self):
        normalized = ContentArticleService.normalize_references_json(
            {"title": "指南", "url": "https://example.com/guideline", "source_type": "guideline"}
        )
        self.assertEqual(normalized[0]["title"], "指南")
        self.assertEqual(normalized[0]["url"], "https://example.com/guideline")
        self.assertEqual(normalized[0]["source"], "guideline")

    def test_generate_unique_slug_retries_when_duplicate_exists(self):
        user = get_user_model().objects.create_user(username="editor", password="pass123456")
        ContentArticle.objects.create(title="已有文章", slug="aaaaaaaaaaaaaa", locale="zh-CN", content="# 内容", author=user)

        with patch("content.services.secrets.choice", side_effect=list("a" * 14 + "b" * 14)):
            slug = ContentArticleService.generate_unique_slug()

        self.assertEqual(slug, "bbbbbbbbbbbbbb")


class ContentArticleApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="admin",
            email="admin@example.com",
            password="pass123456",
            is_staff=True,
            is_superuser=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.category = ContentCategory.objects.create(name="健康科普", slug="health")
        self.tag = ContentTag.objects.create(name="高血压", slug="hypertension")

    def test_create_publish_public_read_and_duration(self):
        create_resp = self.client.post(
            "/api/admin/v1/content/articles/",
            {
                "title": "高血压用药注意事项",
                "locale": "zh-CN",
                "summary": "摘要",
                "content": "# 标题\n\n正文",
                "category_id": self.category.id,
                "tag_ids": [self.tag.id],
                "visibility": ContentArticle.Visibility.PUBLIC,
                "source_url": "https://example.com/source",
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        article_id = create_resp.data["data"]["id"]
        generated_slug = create_resp.data["data"]["slug"]
        self.assertRegex(generated_slug, r"^[a-z0-9]{12,16}$")

        publish_resp = self.client.post(f"/api/admin/v1/content/articles/{article_id}/publish/", {"comment": "test"}, format="json")
        self.assertEqual(publish_resp.status_code, 200)
        self.assertEqual(publish_resp.data["data"]["article"]["status"], ContentArticle.Status.PUBLISHED)

        self.client.force_authenticate(user=None)
        detail_resp = self.client.get(f"/api/v1/content/articles/{generated_slug}/?locale=zh-CN")
        self.assertEqual(detail_resp.status_code, 200)
        self.assertEqual(detail_resp.data["data"]["title"], "高血压用药注意事项")

        detail_by_id_resp = self.client.get(f"/api/v1/content/articles/{article_id}/?locale=zh-CN")
        self.assertEqual(detail_by_id_resp.status_code, 200)
        self.assertEqual(detail_by_id_resp.data["data"]["slug"], generated_slug)

        string_reference_article = ContentArticle.objects.create(
            title="字符串参考文献",
            slug="string-reference",
            locale="zh-CN",
            content="# 内容",
            author=self.user,
            category=self.category,
            status=ContentArticle.Status.PUBLISHED,
            visibility=ContentArticle.Visibility.PUBLIC,
            references_json="https://example.com/reference",
            published_at=timezone.now(),
        )
        string_reference_resp = self.client.get(f"/api/v1/content/articles/{string_reference_article.id}/?locale=zh-CN")
        self.assertEqual(string_reference_resp.status_code, 200)
        self.assertEqual(
            string_reference_resp.data["data"]["references_json"],
            [{"title": "https://example.com/reference", "url": "https://example.com/reference", "source": None, "published_at": None}],
        )
        self.assertEqual(string_reference_resp.data["data"]["references"], string_reference_resp.data["data"]["references_json"])

        view_resp = self.client.post(f"/api/v1/content/articles/{article_id}/view/", {"locale": "zh-CN"}, format="json")
        self.assertEqual(view_resp.status_code, 200)
        duration_resp = self.client.post(
            f"/api/v1/content/articles/{article_id}/reading-duration/",
            {"locale": "zh-CN", "duration_seconds": 35},
            format="json",
        )
        self.assertEqual(duration_resp.status_code, 200)

        article = ContentArticle.objects.get(id=article_id)
        self.assertEqual(article.view_count, 1)
        self.assertEqual(article.read_count, 1)
        self.assertEqual(article.reading_time_seconds, 35)

    def test_publish_requires_reference(self):
        article = ContentArticle.objects.create(
            title="缺少来源",
            slug="missing-reference",
            locale="zh-CN",
            content="# 内容",
            author=self.user,
            category=self.category,
        )
        resp = self.client.post(f"/api/admin/v1/content/articles/{article.id}/publish/", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_public_article_list_supports_pagination_and_etag(self):
        for index in range(3):
            ContentArticle.objects.create(
                title=f"科普文章 {index}",
                slug=f"article-{index}",
                locale="zh-CN",
                summary="摘要",
                content="# 内容",
                author=self.user,
                category=self.category,
                status=ContentArticle.Status.PUBLISHED,
                visibility=ContentArticle.Visibility.PUBLIC,
                source_url="https://example.com/source",
                published_at=timezone.now(),
            )

        self.client.force_authenticate(user=None)
        resp = self.client.get("/api/v1/content/articles/?locale=zh-CN&page=1&page_size=2")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ETag", resp)
        self.assertIn("max-age=86400", resp["Cache-Control"])
        self.assertEqual(len(resp.data["data"]["items"]), 2)
        self.assertEqual(resp.data["data"]["pagination"]["page"], 1)
        self.assertEqual(resp.data["data"]["pagination"]["page_size"], 2)
        self.assertEqual(resp.data["data"]["pagination"]["total"], 3)
        self.assertEqual(resp.data["data"]["pagination"]["total_pages"], 2)
        self.assertTrue(resp.data["data"]["pagination"]["has_next"])
        self.assertEqual(resp.data["data"]["pagination"]["next_page"], 2)

        cached_resp = self.client.get(
            "/api/v1/content/articles/?locale=zh-CN&page=1&page_size=2",
            HTTP_IF_NONE_MATCH=resp["ETag"],
        )
        self.assertEqual(cached_resp.status_code, 304)
        self.assertEqual(cached_resp["ETag"], resp["ETag"])
        self.assertIn("max-age=86400", cached_resp["Cache-Control"])
        self.assertEqual(cached_resp.content, b"")

        client_ttl_resp = self.client.get(
            "/api/v1/content/articles/?locale=zh-CN&page=1&page_size=2",
            HTTP_X_CACHE_MAX_AGE="3600",
        )
        self.assertIn("max-age=3600", client_ttl_resp["Cache-Control"])

    def test_public_categories_support_etag(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get("/api/v1/content/categories/?locale=zh-CN")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ETag", resp)
        self.assertIn("max-age=86400", resp["Cache-Control"])

        cached_resp = self.client.get("/api/v1/content/categories/?locale=zh-CN", HTTP_IF_NONE_MATCH=resp["ETag"])
        self.assertEqual(cached_resp.status_code, 304)
        self.assertEqual(cached_resp.content, b"")

    def test_public_article_detail_by_id_supports_etag(self):
        article = ContentArticle.objects.create(
            title="详情缓存文章",
            slug="detail-cache",
            locale="zh-CN",
            summary="摘要",
            content="# 内容",
            author=self.user,
            category=self.category,
            status=ContentArticle.Status.PUBLISHED,
            visibility=ContentArticle.Visibility.PUBLIC,
            source_url="https://example.com/source",
            published_at=timezone.now(),
        )

        self.client.force_authenticate(user=None)
        resp = self.client.get(f"/api/v1/content/articles/{article.id}/?locale=zh-CN")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ETag", resp)
        self.assertIn("max-age=86400", resp["Cache-Control"])

        cached_resp = self.client.get(f"/api/v1/content/articles/{article.id}/?locale=zh-CN", HTTP_IF_NONE_MATCH=resp["ETag"])
        self.assertEqual(cached_resp.status_code, 304)
        self.assertEqual(cached_resp.content, b"")
