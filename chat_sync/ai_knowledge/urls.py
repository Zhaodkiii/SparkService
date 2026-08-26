from django.urls import path

from chat_sync.ai_knowledge.api.views import (
    KnowledgeDefaultBaseView,
    KnowledgeSyncPullView,
    KnowledgeSyncPushView,
)

urlpatterns = [
    path("default/", KnowledgeDefaultBaseView.as_view(), name="knowledge_default_base"),
    path("sync/push/", KnowledgeSyncPushView.as_view(), name="knowledge_sync_push"),
    path("sync/pull/", KnowledgeSyncPullView.as_view(), name="knowledge_sync_pull"),
]
