from django.urls import path

from chat_sync.consumers import ChatSyncConsumer
from chat_sync.ai_routing import websocket_urlpatterns as ai_websocket_urlpatterns

websocket_urlpatterns = [
    path("ws/chat/sync/", ChatSyncConsumer.as_asgi()),
] + ai_websocket_urlpatterns
