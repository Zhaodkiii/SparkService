"""Decrypt legacy Fernet-encrypted provider API keys."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)
_FERNET_PREFIX = b"gAAAAA"


def decrypt_legacy_api_key(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        raw = ciphertext.encode("ascii") if isinstance(ciphertext, str) else ciphertext
        if not raw.startswith(_FERNET_PREFIX):
            return ciphertext
    except (UnicodeEncodeError, AttributeError):
        return ciphertext

    key = (os.getenv("AI_PROVIDER_KEY_ENCRYPTION_KEY") or "").strip()
    if not key:
        logger.warning("AI_PROVIDER_KEY_ENCRYPTION_KEY not set; returning ciphertext as-is")
        return ciphertext
    try:
        from cryptography.fernet import Fernet

        f = Fernet(key.encode() if isinstance(key, str) else key)
        return f.decrypt(raw).decode("utf-8")
    except Exception as exc:
        logger.warning("Failed to decrypt legacy API key: %s", exc)
        return ""
