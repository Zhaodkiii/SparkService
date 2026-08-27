from django.urls import path

from chat_sync.ai_knowledge.api.views import (
    KnowledgeBaseCollectionView,
    KnowledgeBaseDetailView,
    KnowledgeDefaultBaseView,
    KnowledgeDocumentCollectionView,
    KnowledgeDocumentDetailView,
    KnowledgeFileCollectionView,
    KnowledgeFileDetailView,
    KnowledgeIndexJobView,
    KnowledgeIndexVersionView,
    KnowledgeSearchView,
    KnowledgeSyncPullView,
    KnowledgeSyncPushView,
)

urlpatterns = [
    path("default/", KnowledgeDefaultBaseView.as_view(), name="knowledge_default_base"),
    path("sync/push/", KnowledgeSyncPushView.as_view(), name="knowledge_sync_push"),
    path("sync/pull/", KnowledgeSyncPullView.as_view(), name="knowledge_sync_pull"),
    path("bases/", KnowledgeBaseCollectionView.as_view(), name="knowledge_bases"),
    path("bases/<uuid:base_id>/", KnowledgeBaseDetailView.as_view(), name="knowledge_base_detail"),
    path("bases/<uuid:base_id>/documents/", KnowledgeDocumentCollectionView.as_view(), name="knowledge_documents"),
    path("documents/<uuid:document_id>/", KnowledgeDocumentDetailView.as_view(), name="knowledge_document_detail"),
    path("bases/<uuid:base_id>/files/", KnowledgeFileCollectionView.as_view(), name="knowledge_files"),
    path("bases/<uuid:base_id>/files/<uuid:file_uuid>/", KnowledgeFileDetailView.as_view(), name="knowledge_file_detail"),
    path("bases/<uuid:base_id>/index-versions/", KnowledgeIndexVersionView.as_view(), name="knowledge_index_versions"),
    path("bases/<uuid:base_id>/index-jobs/", KnowledgeIndexJobView.as_view(), name="knowledge_index_jobs"),
    path("search/", KnowledgeSearchView.as_view(), name="knowledge_search"),
]
