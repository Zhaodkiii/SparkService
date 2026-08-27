import json
import ssl
from typing import Any
from urllib.request import urlopen

import jwt
from django.conf import settings
from django.core.cache import cache
import logging

from common.exceptions import APIError

APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_CACHE_KEY = "sparkservice:apple:jwks"

logger = logging.getLogger(__name__)
flow_logger = logging.getLogger("accounts.flow")


class AppleIdentityService:
    @staticmethod
    def verify_identity_token(identity_token: str, audiences: list[str]) -> tuple[dict[str, Any], str]:
        flow_logger.info(
            "Apple 身份令牌校验开始",
            extra={"action": "auth.apple.identity.verify", "audiences": audiences},
        )
        if not identity_token:
            flow_logger.warning(
                "Apple 身份令牌校验失败：缺少 identity_token",
                extra={"action": "auth.apple.identity.verify", "outcome": "failed", "reason": "identity_token_required"},
            )
            raise APIError("identity_token required", code=40021, status_code=400)

        unverified_header = jwt.get_unverified_header(identity_token)
        key_id = unverified_header.get("kid")
        algorithm = unverified_header.get("alg", "RS256")
        if not key_id:
            flow_logger.warning(
                "Apple 身份令牌校验失败：缺少 kid",
                extra={"action": "auth.apple.identity.verify", "outcome": "failed", "reason": "apple_token_kid_missing"},
            )
            raise APIError("apple_token_kid_missing", code=40022, status_code=400)

        jwks = AppleIdentityService._load_jwks()
        jwk = next((item for item in jwks if item.get("kid") == key_id), None)
        if not jwk:
            cache.delete(APPLE_JWKS_CACHE_KEY)
            jwks = AppleIdentityService._load_jwks(force_refresh=True)
            jwk = next((item for item in jwks if item.get("kid") == key_id), None)
        if not jwk:
            flow_logger.warning(
                "Apple 身份令牌校验失败：未找到对应公钥",
                extra={"action": "auth.apple.identity.verify", "outcome": "failed", "reason": "apple_public_key_not_found"},
            )
            raise APIError("apple_public_key_not_found", code=40121, status_code=401)

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
        verify_errors: list[str] = []
        leeway_seconds = int(getattr(settings, "APPLE_IDENTITY_TOKEN_LEEWAY_SECONDS", 30))

        for aud in audiences:
            if not aud:
                continue
            try:
                payload = jwt.decode(
                    identity_token,
                    key=public_key,
                    algorithms=[algorithm],
                    audience=aud,
                    issuer=APPLE_ISSUER,
                    options={"require": ["exp", "iat", "iss", "aud", "sub"]},
                    leeway=leeway_seconds,
                )
                flow_logger.info(
                    "Apple 身份令牌校验成功",
                    extra={"action": "auth.apple.identity.verify", "outcome": "success", "matched_audience": aud},
                )
                return payload, aud
            except jwt.InvalidAudienceError as exc:
                verify_errors.append(str(exc))
            except (jwt.ImmatureSignatureError, jwt.ExpiredSignatureError, jwt.InvalidIssuedAtError) as exc:
                flow_logger.warning(
                    "Apple 身份令牌校验失败：token 时间无效",
                    extra={
                        "action": "auth.apple.identity.verify",
                        "outcome": "failed",
                        "reason": "apple_token_time_invalid",
                        "leeway_seconds": leeway_seconds,
                    },
                )
                raise APIError(
                    "apple_token_time_invalid",
                    code=40125,
                    status_code=401,
                    details={"error": str(exc), "leeway_seconds": leeway_seconds},
                ) from exc
            except jwt.InvalidTokenError as exc:
                flow_logger.warning(
                    "Apple 身份令牌校验失败：token 无效",
                    extra={"action": "auth.apple.identity.verify", "outcome": "failed", "reason": "apple_identity_token_invalid"},
                )
                raise APIError(
                    "apple_identity_token_invalid",
                    code=40126,
                    status_code=401,
                    details={"error": str(exc)},
                ) from exc

        flow_logger.warning(
            "Apple 身份令牌校验失败：aud 不匹配",
            extra={"action": "auth.apple.identity.verify", "outcome": "failed", "reason": "apple_audience_mismatch"},
        )
        raise APIError(
            "apple_audience_mismatch",
            code=40122,
            status_code=401,
            details={"allowed_audiences": audiences, "errors": verify_errors[-3:]},
        )

    @staticmethod
    def _load_jwks(force_refresh: bool = False) -> list[dict[str, Any]]:
        flow_logger.info(
            "从 Apple 获取 JWKS 公钥列表开始",
            extra={"action": "auth.apple.jwks.fetch", "force_refresh": force_refresh},
        )
        if force_refresh is False:
            cached = cache.get(APPLE_JWKS_CACHE_KEY)
            if cached:
                flow_logger.info(
                    "从缓存命中 Apple JWKS 公钥列表",
                    extra={"action": "auth.apple.jwks.fetch", "source": "cache"},
                )
                return cached

        payload: dict[str, Any] | None = None
        last_error: Exception | None = None
        verify_ssl = bool(getattr(settings, "APPLE_JWKS_VERIFY_SSL", True))
        timeout = int(getattr(settings, "APPLE_JWKS_TIMEOUT_SECONDS", 8))
        try:
            context: ssl.SSLContext | None = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
            with urlopen(APPLE_KEYS_URL, timeout=timeout, context=context) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last_error = exc

        if payload is None:
            logger.error("apple_jwks_fetch_failed", extra={"reason": str(last_error) if last_error else "unknown"})
            flow_logger.error(
                "从 Apple 获取 JWKS 公钥列表失败",
                extra={
                    "action": "auth.apple.jwks.fetch",
                    "outcome": "failed",
                    "reason": str(last_error) if last_error else "unknown",
                    "error_code": "apple_jwks_unavailable",
                },
            )
            raise APIError(
                "apple_jwks_unavailable",
                code=50321,
                status_code=503,
                details={"reason": str(last_error) if last_error else "unknown"},
            )

        keys = payload.get("keys", [])
        if not isinstance(keys, list) or not keys:
            flow_logger.error(
                "从 Apple 获取 JWKS 公钥列表失败：返回数据无效",
                extra={"action": "auth.apple.jwks.fetch", "outcome": "failed", "error_code": "apple_jwks_invalid"},
            )
            raise APIError("apple_jwks_invalid", code=50322, status_code=503)

        ttl = int(getattr(settings, "APPLE_JWKS_TTL_SECONDS", 3600))
        cache.set(APPLE_JWKS_CACHE_KEY, keys, timeout=ttl)
        flow_logger.info(
            "从 Apple 获取 JWKS 公钥列表成功",
            extra={"action": "auth.apple.jwks.fetch", "outcome": "success", "keys_count": len(keys)},
        )
        return keys
