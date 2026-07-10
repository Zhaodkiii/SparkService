from django.urls import path

from content.views import (
    AdminContentAnalyticsView,
    AdminContentArticleArchiveView,
    AdminContentArticleDetailView,
    AdminContentArticleListCreateView,
    AdminContentArticleOfflineView,
    AdminContentArticlePreviewView,
    AdminContentArticlePublishView,
    AdminContentArticleRestoreView,
    AdminContentArticleRollbackView,
    AdminContentArticleShareLinkView,
    AdminContentArticleSqlExportView,
    AdminContentArticleVersionListView,
    AdminContentCategoryDetailView,
    AdminContentCategoryListCreateView,
    AdminContentComplianceView,
    AdminContentOverviewView,
    AdminContentTagDetailView,
    AdminContentTagListCreateView,
    AdminContentTagMergeView,
)


urlpatterns = [
    path("overview/", AdminContentOverviewView.as_view(), name="admin-content-overview"),
    path("analytics/", AdminContentAnalyticsView.as_view(), name="admin-content-analytics"),
    path("compliance/", AdminContentComplianceView.as_view(), name="admin-content-compliance"),
    path("articles/", AdminContentArticleListCreateView.as_view(), name="admin-content-article-list-create"),
    path("articles/export-sql/", AdminContentArticleSqlExportView.as_view(), name="admin-content-article-export-sql"),
    path("articles/<int:article_id>/", AdminContentArticleDetailView.as_view(), name="admin-content-article-detail"),
    path("articles/<int:article_id>/publish/", AdminContentArticlePublishView.as_view(), name="admin-content-article-publish"),
    path("articles/<int:article_id>/offline/", AdminContentArticleOfflineView.as_view(), name="admin-content-article-offline"),
    path("articles/<int:article_id>/archive/", AdminContentArticleArchiveView.as_view(), name="admin-content-article-archive"),
    path("articles/<int:article_id>/restore/", AdminContentArticleRestoreView.as_view(), name="admin-content-article-restore"),
    path("articles/<int:article_id>/preview/", AdminContentArticlePreviewView.as_view(), name="admin-content-article-preview"),
    path("articles/<int:article_id>/share-link/", AdminContentArticleShareLinkView.as_view(), name="admin-content-article-share-link"),
    path("articles/<int:article_id>/versions/", AdminContentArticleVersionListView.as_view(), name="admin-content-article-version-list"),
    path("articles/<int:article_id>/versions/<int:version_id>/rollback/", AdminContentArticleRollbackView.as_view(), name="admin-content-article-rollback"),
    path("categories/", AdminContentCategoryListCreateView.as_view(), name="admin-content-category-list-create"),
    path("categories/<int:category_id>/", AdminContentCategoryDetailView.as_view(), name="admin-content-category-detail"),
    path("tags/", AdminContentTagListCreateView.as_view(), name="admin-content-tag-list-create"),
    path("tags/<int:tag_id>/", AdminContentTagDetailView.as_view(), name="admin-content-tag-detail"),
    path("tags/merge/", AdminContentTagMergeView.as_view(), name="admin-content-tag-merge"),
]

