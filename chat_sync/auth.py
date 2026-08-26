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
    user, _claims = resolve_auth_from_ticket_sync(raw_ticket, websocket_path)
    return user


def resolve_auth_from_ticket_sync(raw_ticket: str | None, websocket_path: str):
    if not raw_ticket:
        return AnonymousUser(), {}
    from chat_sync.ai_models import ChatWebSocketTicket
    from accounts.services.web_session_service import WebSessionService

    token_hash = hashlib.sha256(raw_ticket.encode("utf-8")).hexdigest()
    with transaction.atomic():
        ticket = ChatWebSocketTicket.objects.select_for_update().select_related("user").filter(token_hash=token_hash).first()
        if ticket is None or ticket.used_at is not None or ticket.expires_at <= timezone.now():
            return AnonymousUser(), {}
        if ticket.websocket_path != websocket_path:
            return AnonymousUser(), {}
        claims = {}
        if ticket.web_session_id is not None:
            claims = {
                "web_session_id": str(ticket.web_session_id),
                "web_session_version": ticket.web_session_version or 0,
                "session_class": "web",
            }
            try:
                WebSessionService.validate_access_claims(user=ticket.user, validated_token=claims)
            except Exception:
                return AnonymousUser(), {}
        ticket.used_at = timezone.now()
        ticket.save(update_fields=["used_at"])
        return ticket.user, claims


@database_sync_to_async
def resolve_auth_from_ticket(raw_ticket: str | None, websocket_path: str):
    return resolve_auth_from_ticket_sync(raw_ticket, websocket_path)

@database_sync_to_async
def resolve_auth_from_token(raw_token: str):
    if raw_token is None or raw_token == "":
        return AnonymousUser(), {}

    class _BearerRequest:
        META = {"HTTP_AUTHORIZATION": f"Bearer {raw_token}"}

    try:
        result = SparkJWTAuthentication().authenticate(_BearerRequest())
        if result is None:
            return AnonymousUser(), {}
        user, validated_token = result
        claims = dict(getattr(validated_token, "payload", {}) or {})
        return user, claims
    except Exception:
        logger.warning("chat ws token validation failed")
        return AnonymousUser(), {}


async def resolve_user_from_token(raw_token: str):
    """Backward-compatible user-only resolver for non-session WS callers."""
    user, _claims = await resolve_auth_from_token(raw_token)
    return user


class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        ticket = (query.get("ticket") or [None])[0]
        websocket_path = scope.get("path") or ""
        if ticket is not None:
            user, claims = await resolve_auth_from_ticket(ticket, websocket_path)
            scope["user"] = user
            scope["auth_claims"] = claims
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

        user, claims = await resolve_auth_from_token(token)
        scope["user"] = user
        scope["auth_claims"] = claims
        return await self.inner(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)
