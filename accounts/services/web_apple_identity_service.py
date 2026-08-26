"""Web Apple identity verification (CHAT-WEB-019C).

Isolated from the mobile AppleIdentityService contract: separate JWKS cache
key, strict TLS by default, nonce required, audience restricted to the
configured Web Service IDs, and server-side authorization code exchange.

This module must stay independent of AppleIdentityService so the mobile
baseline (including its `apple_jwks_unavailable` behavior) is untouched.
"""

from __future__ import annotations

import hashlib
import json
import logging
import ssl
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import jwt
from django.conf import settings
from django.core.cache import cache

from common.exceptions import APIError

APPLE_WEB_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_WEB_ISSUER = "https://appleid.apple.com"
APPLE_WEB_JWKS_CACHE_KEY = "sparkservice:apple_web:jwks"

logger = logging.getLogger(__name__)
flow_logger = logging.getLogger("accounts.flow")


class WebAppleIdentityService:
    """Strict verification pipeline for Chat Web Apple sign-in."""

    @staticmethod
    def _leeway_seconds() -> int:
        return int(getattr(settings, "APPLE_IDENTITY_TOKEN_LEEWAY_SECONDS", 30))

    @staticmethod
    def _raise_invalid(reason: str, *, details: dict[str, Any] | None = None) -> None:
        flow_logger.warning(
            "Web Apple 身份令牌校验失败",
            extra={
                "action": "auth.apple.web.identity.verify",
                "outcome": "failed",
                "reason": reason,
            },
        )
        raise APIError("apple_web_token_invalid", code=40172, status_code=401, details=details or {})

    @staticmethod
    def validate_service_id(service_id: str) -> str:
        normalized = (service_id or "").strip()
        allowed = list(getattr(settings, "APPLE_WEB_SERVICE_IDS", []) or [])
        if not normalized or not allowed or normalized not in allowed:
            raise APIError("apple_web_callback_invalid", code=40071, status_code=400)
        return normalized

    @staticmethod
    def validate_redirect_uri(redirect_uri: str) -> str:
        normalized = (redirect_uri or "").strip()
        allowed = list(getattr(settings, "APPLE_WEB_ALLOWED_REDIRECT_URIS", []) or [])
        if not normalized or not allowed or normalized not in allowed:
            raise APIError("apple_web_callback_invalid", code=40071, status_code=400)
        if not normalized.lower().startswith("https://"):
            raise APIError("apple_web_callback_invalid", code=40071, status_code=400)
        return normalized

    @staticmethod
    def verify_nonce(*, payload: dict[str, Any], nonce: str) -> None:
        """Web flow: nonce is mandatory and must match exactly (sha256)."""
        presented_nonce = (nonce or "").strip()
        token_nonce = (payload.get("nonce") or "").strip()
        if not presented_nonce or not token_nonce:
            raise APIError("apple_web_nonce_mismatch", code=40171, status_code=401)
        expected = hashlib.sha256(presented_nonce.encode("utf-8")).hexdigest()
        if token_nonce != expected:
            raise APIError("apple_web_nonce_mismatch", code=40171, status_code=401)

    @staticmethod
    def _load_jwks(force_refresh: bool = False) -> list[dict[str, Any]]:
        flow_logger.info(
            "Web Apple JWKS 拉取开始",
            extra={"action": "auth.apple.web.jwks.fetch", "force_refresh": force_refresh},
        )
        if not force_refresh:
            cached = cache.get(APPLE_WEB_JWKS_CACHE_KEY)
            if cached:
                return cached

        payload: dict[str, Any] | None = None
        last_error: Exception | None = None
        verify_ssl = bool(getattr(settings, "APPLE_WEB_JWKS_VERIFY_SSL", True))
        timeout = int(getattr(settings, "APPLE_WEB_JWKS_TIMEOUT_SECONDS", 8))
        try:
            context = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
            with urlopen(APPLE_WEB_KEYS_URL, timeout=timeout, context=context) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last_error = exc

        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list) or not payload["keys"]:
            flow_logger.error(
                "Web Apple JWKS 拉取失败",
                extra={
                    "action": "auth.apple.web.jwks.fetch",
                    "outcome": "failed",
                    "error_code": "apple_web_jwks_unavailable",
                    "reason": str(last_error) if last_error else "invalid_payload",
                },
            )
            raise APIError("apple_web_jwks_unavailable", code=50371, status_code=503)

        keys = payload["keys"]
        ttl = int(getattr(settings, "APPLE_WEB_JWKS_TTL_SECONDS", 3600))
        cache.set(APPLE_WEB_JWKS_CACHE_KEY, keys, timeout=ttl)
        flow_logger.info(
            "Web Apple JWKS 拉取成功",
            extra={"action": "auth.apple.web.jwks.fetch", "outcome": "success", "keys_count": len(keys)},
        )
        return keys

    @staticmethod
    def _resolve_jwk(identity_token: str) -> tuple[dict[str, Any], str]:
        try:
            unverified_header = jwt.get_unverified_header(identity_token)
        except jwt.InvalidTokenError as exc:
            WebAppleIdentityService._raise_invalid("header_unparsable", details={"error": str(exc)})
        key_id = unverified_header.get("kid")
        algorithm = unverified_header.get("alg", "RS256")
        if not key_id:
            WebAppleIdentityService._raise_invalid("kid_missing")

        jwks = WebAppleIdentityService._load_jwks()
        jwk = next((item for item in jwks if item.get("kid") == key_id), None)
        if jwk is None:
            # Unknown kid: force one refresh, then reject if still missing.
            cache.delete(APPLE_WEB_JWKS_CACHE_KEY)
            jwks = WebAppleIdentityService._load_jwks(force_refresh=True)
            jwk = next((item for item in jwks if item.get("kid") == key_id), None)
        if jwk is None:
            WebAppleIdentityService._raise_invalid("unknown_kid")
        return jwk, algorithm

    @staticmethod
    def verify_identity_token(*, identity_token: str, service_id: str, nonce: str) -> dict[str, Any]:
        """Verify the Web identity token: TLS/JWKS/iss/aud/exp/iat/sub/nonce."""
        flow_logger.info(
            "Web Apple 身份令牌校验开始",
            extra={"action": "auth.apple.web.identity.verify"},
        )
        if not (identity_token or "").strip():
            raise APIError("apple_web_callback_invalid", code=40071, status_code=400)
        service_id = WebAppleIdentityService.validate_service_id(service_id)

        jwk, algorithm = WebAppleIdentityService._resolve_jwk(identity_token)
        try:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
        except (ValueError, TypeError) as exc:
            WebAppleIdentityService._raise_invalid("jwk_invalid", details={"error": str(exc)})

        try:
            payload = jwt.decode(
                identity_token,
                key=public_key,
                algorithms=[algorithm],
                audience=service_id,
                issuer=APPLE_WEB_ISSUER,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
                leeway=WebAppleIdentityService._leeway_seconds(),
            )
        except (jwt.ImmatureSignatureError, jwt.ExpiredSignatureError, jwt.InvalidIssuedAtError) as exc:
            WebAppleIdentityService._raise_invalid("token_time_invalid", details={"error": str(exc)})
        except jwt.InvalidAudienceError as exc:
            WebAppleIdentityService._raise_invalid("audience_mismatch", details={"error": str(exc)})
        except jwt.InvalidTokenError as exc:
            WebAppleIdentityService._raise_invalid("token_invalid", details={"error": str(exc)})

        WebAppleIdentityService.verify_nonce(payload=payload, nonce=nonce)
        flow_logger.info(
            "Web Apple 身份令牌校验成功",
            extra={"action": "auth.apple.web.identity.verify", "outcome": "success"},
        )
        return payload

    @staticmethod
    def _build_client_secret(*, service_id: str) -> str:
        team_id = (getattr(settings, "APPLE_WEB_TEAM_ID", "") or "").strip()
        key_id = (getattr(settings, "APPLE_WEB_KEY_ID", "") or "").strip()
        private_key = (getattr(settings, "APPLE_WEB_PRIVATE_KEY", "") or "").strip()
        if not team_id or not key_id or not private_key:
            raise APIError("apple_web_code_exchange_unavailable", code=50372, status_code=503)
        now = int(time.time())
        ttl = 1800
        headers = {"alg": "ES256", "kid": key_id}
        claims = {
            "iss": team_id,
            "iat": now,
            "exp": now + ttl,
            "aud": APPLE_WEB_ISSUER,
            "sub": service_id,
        }
        return jwt.encode(claims, private_key, algorithm="ES256", headers=headers)

    @staticmethod
    def exchange_authorization_code(
        *,
        authorization_code: str,
        service_id: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        """Exchange the authorization code server-side and validate the response.

        Returns the parsed token endpoint payload. The caller must verify the
        returned id_token subject matches the identity token subject.
        """
        code = (authorization_code or "").strip()
        if not code:
            raise APIError("apple_web_callback_invalid", code=40071, status_code=400)
        service_id = WebAppleIdentityService.validate_service_id(service_id)
        redirect_uri = WebAppleIdentityService.validate_redirect_uri(redirect_uri)
        client_secret = WebAppleIdentityService._build_client_secret(service_id=service_id)

        endpoint = (getattr(settings, "APPLE_WEB_TOKEN_ENDPOINT", "") or "").strip()
        form = json.dumps(
            {
                "client_id": service_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            }
        ).encode("utf-8")
        request = Request(
            endpoint,
            data=form,
            headers={"content-type": "application/json", "accept": "application/json"},
            method="POST",
        )
        try:
            context = ssl.create_default_context()
            with urlopen(request, timeout=int(getattr(settings, "APPLE_WEB_JWKS_TIMEOUT_SECONDS", 8)), context=context) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            flow_logger.error(
                "Web Apple code 兑换失败",
                extra={
                    "action": "auth.apple.web.code.exchange",
                    "outcome": "failed",
                    "error_code": "apple_web_code_exchange_unavailable",
                    "reason": str(exc),
                },
            )
            raise APIError("apple_web_code_exchange_unavailable", code=50372, status_code=503) from exc
        except Exception as exc:  # noqa: BLE001
            flow_logger.error(
                "Web Apple code 兑换失败",
                extra={
                    "action": "auth.apple.web.code.exchange",
                    "outcome": "failed",
                    "error_code": "apple_web_code_exchange_unavailable",
                    "reason": str(exc),
                },
            )
            raise APIError("apple_web_code_exchange_unavailable", code=50372, status_code=503) from exc

        if not isinstance(payload, dict) or not payload.get("id_token"):
            raise APIError("apple_web_code_exchange_unavailable", code=50372, status_code=503)
        flow_logger.info(
            "Web Apple code 兑换成功",
            extra={"action": "auth.apple.web.code.exchange", "outcome": "success"},
        )
        return payload

    @staticmethod
    def verify_code_exchange_subject(*, exchanged_id_token: str, expected_subject: str) -> None:
        """The id_token returned by the code exchange must carry the same subject."""
        try:
            unverified = jwt.decode(exchanged_id_token, options={"verify_signature": False})
        except jwt.InvalidTokenError as exc:
            WebAppleIdentityService._raise_invalid("code_exchange_token_invalid", details={"error": str(exc)})
        subject = (unverified.get("sub") or "").strip()
        if not subject or subject != (expected_subject or "").strip():
            WebAppleIdentityService._raise_invalid("code_exchange_subject_mismatch")
