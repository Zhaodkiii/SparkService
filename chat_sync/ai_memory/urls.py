from django.urls import path

from chat_sync.ai_memory.api.views import (
    MemoryEntryCollectionView,
    MemoryEntryDetailView,
    MemorySyncPullView,
    MemorySyncPushView,
)

urlpatterns = [
    path("entries/", MemoryEntryCollectionView.as_view(), name="memory_entries"),
    path("entries/<uuid:memory_id>/", MemoryEntryDetailView.as_view(), name="memory_entry_detail"),
    path("sync/push/", MemorySyncPushView.as_view(), name="memory_sync_push"),
    path("sync/pull/", MemorySyncPullView.as_view(), name="memory_sync_pull"),
]
