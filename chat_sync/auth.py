from urllib.parse import parse_qs
import logging

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication

logger = logging.getLogger("chat_sync.ws")

@database_sync_to_async
def resolve_user_from_token(raw_token: str):
    if raw_token is None or raw_token == "":
        return AnonymousUser()

    authenticator = JWTAuthentication()
    try:
        validated = authenticator.get_validated_token(raw_token)
        return authenticator.get_user(validated)
    except Exception:
        logger.warning("chat ws token validation failed")
        return AnonymousUser()


class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = (query.get("token") or [None])[0]

        if token is None:
            for header_name, header_value in scope.get("headers", []):
                if header_name == b"authorization":
                    value = header_value.decode()
                    if value.lower().startswith("bearer "):
                        token = value.split(" ", 1)[1].strip()
                    break

        scope["user"] = await resolve_user_from_token(token)
        return await self.inner(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)
