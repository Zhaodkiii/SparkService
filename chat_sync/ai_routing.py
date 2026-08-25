from django.urls import path

from chat_sync.ai_consumers import ChatRunConsumer

websocket_urlpatterns = [path("ws/chat/runs/", ChatRunConsumer.as_asgi())]

