from celery import shared_task
from django.utils import timezone

from content.models import ContentArticle
from content.services import ContentArticleService


@shared_task
def publish_due_content_articles_task():
    """
    发布到达定时时间的草稿文章。
    """
    due_articles = ContentArticle.objects.filter(
        deleted_at__isnull=True,
        status=ContentArticle.Status.DRAFT,
        published_at__isnull=False,
        published_at__lte=timezone.now(),
    )
    count = 0
    for article in due_articles:
        try:
            ContentArticleService.publish_article(article.author, article, published_at=article.published_at, comment="scheduled_publish")
            count += 1
        except Exception:
            continue
    return {"published": count}
