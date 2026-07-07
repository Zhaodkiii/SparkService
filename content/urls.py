from django.urls import path

from content.views import (
    PublicContentArticleDetailByIDView,
    PublicContentArticleDetailView,
    PublicContentArticleListView,
    PublicContentArticleReadingDurationView,
    PublicContentArticleShareLinkView,
    PublicContentArticleViewEventView,
    PublicContentCategoryListView,
    PublicContentTagListView,
)


urlpatterns = [
    path("articles/", PublicContentArticleListView.as_view(), name="content-article-list"),
    path("articles/<int:article_id>/view/", PublicContentArticleViewEventView.as_view(), name="content-article-view"),
    path("articles/<int:article_id>/reading-duration/", PublicContentArticleReadingDurationView.as_view(), name="content-article-reading-duration"),
    path("articles/<int:article_id>/share-link/", PublicContentArticleShareLinkView.as_view(), name="content-article-share-link"),
    path("articles/<int:article_id>/", PublicContentArticleDetailByIDView.as_view(), name="content-article-detail-by-id"),
    path("articles/<slug:slug>/", PublicContentArticleDetailView.as_view(), name="content-article-detail"),
    path("categories/", PublicContentCategoryListView.as_view(), name="content-category-list"),
    path("tags/", PublicContentTagListView.as_view(), name="content-tag-list"),
]

