from django.urls import path

from chat_sync.views import ChatSyncPullView, ChatSyncPushView

urlpatterns = [
    path("sync/push/", ChatSyncPushView.as_view(), name="chat_sync_push"),
    path("sync/pull/", ChatSyncPullView.as_view(), name="chat_sync_pull"),
]
