import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SparkService.settings")

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

# 先初始化 Django ASGI 应用，确保 apps registry 已完成加载。
django_asgi_app = get_asgi_application()

from chat_sync.auth import JWTAuthMiddlewareStack
from chat_sync.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
