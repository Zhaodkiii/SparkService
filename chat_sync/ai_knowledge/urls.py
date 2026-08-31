from django.urls import path

from chat_sync.ai_knowledge.api.views import (
    KnowledgeBaseCollectionView,
    KnowledgeBaseDetailView,
    KnowledgeDefaultBaseView,
    KnowledgeDocumentCollectionView,
    KnowledgeDocumentDetailView,
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
]
