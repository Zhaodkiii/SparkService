from django.urls import path

from chat_sync.consumers import ChatSyncConsumer

websocket_urlpatterns = [
    path("ws/chat/sync/", ChatSyncConsumer.as_asgi()),
]
