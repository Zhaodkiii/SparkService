from django.urls import path

from chat_sync.views import (
    ChatSyncPullView,
    ChatSyncPushView,
    ChatSyncThreadDeleteView,
    ChatSyncThreadHeadView,
    ChatSyncThreadPullView,
    ChatSyncThreadPushView,
)

urlpatterns = [
    path("sync/push/", ChatSyncPushView.as_view(), name="chat_sync_push"),
    path("sync/pull/", ChatSyncPullView.as_view(), name="chat_sync_pull"),
    path("sync/thread-pull/", ChatSyncThreadPullView.as_view(), name="chat_sync_thread_pull"),
    path("sync/thread-push/", ChatSyncThreadPushView.as_view(), name="chat_sync_thread_push"),
    path("sync/thread-delete/", ChatSyncThreadDeleteView.as_view(), name="chat_sync_thread_delete"),
    path("sync/thread-head/", ChatSyncThreadHeadView.as_view(), name="chat_sync_thread_head"),
]
