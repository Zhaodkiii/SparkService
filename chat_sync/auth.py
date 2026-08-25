from urllib.parse import parse_qs
import hashlib
import logging

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.utils import timezone
from accounts.auth.authentication import SparkJWTAuthentication

logger = logging.getLogger("chat_sync.ws")


@database_sync_to_async
def resolve_user_from_ticket(raw_ticket: str | None, websocket_path: str):
    if not raw_ticket:
        return AnonymousUser()
    from chat_sync.ai_models import ChatWebSocketTicket

    token_hash = hashlib.sha256(raw_ticket.encode("utf-8")).hexdigest()
    with transaction.atomic():
        ticket = ChatWebSocketTicket.objects.select_for_update().select_related("user").filter(token_hash=token_hash).first()
        if ticket is None or ticket.used_at is not None or ticket.expires_at <= timezone.now():
            return AnonymousUser()
        if ticket.websocket_path != websocket_path:
            return AnonymousUser()
        ticket.used_at = timezone.now()
        ticket.save(update_fields=["used_at"])
        return ticket.user

@database_sync_to_async
def resolve_user_from_token(raw_token: str):
    if raw_token is None or raw_token == "":
        return AnonymousUser()

    class _BearerRequest:
        META = {"HTTP_AUTHORIZATION": f"Bearer {raw_token}"}

    try:
        result = SparkJWTAuthentication().authenticate(_BearerRequest())
        if result is None:
            return AnonymousUser()
        user, _token = result
        return user
    except Exception:
        logger.warning("chat ws token validation failed")
        return AnonymousUser()


class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        ticket = (query.get("ticket") or [None])[0]
        websocket_path = scope.get("path") or ""
        if ticket is not None:
            scope["user"] = await resolve_user_from_ticket(ticket, websocket_path)
            return await self.inner(scope, receive, send)
        if websocket_path == "/ws/chat/runs/":
            # Browser Run sockets must never fall back to a long-lived JWT query.
            scope["user"] = AnonymousUser()
            return await self.inner(scope, receive, send)
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
