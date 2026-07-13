from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _derive_key(seed: str, *, label: str) -> bytes:
    material = (seed or "").strip() or settings.SECRET_KEY
    return hashlib.sha256(f"notification-center:{label}:{material}".encode("utf-8")).digest()


def _encryption_key() -> bytes:
    seed = os.getenv("NOTIFICATION_CENTER_ENCRYPTION_KEY", "").strip()
    return _derive_key(seed, label="encryption")


def _hmac_key() -> bytes:
    seed = os.getenv("NOTIFICATION_CENTER_HMAC_KEY", "").strip()
    return _derive_key(seed, label="hmac")


def encrypt_sensitive(value: str) -> str:
    plain = (value or "").strip()
    if not plain:
        return ""
    nonce = os.urandom(12)
    cipher = AESGCM(_encryption_key()).encrypt(nonce, plain.encode("utf-8"), None)
    return f"v1:{_b64url_encode(nonce)}:{_b64url_encode(cipher)}"


def decrypt_sensitive(ciphertext: str) -> str:
    token = (ciphertext or "").strip()
    if not token:
        return ""
    if not token.startswith("v1:"):
        return token
    _, nonce_text, cipher_text = token.split(":", 2)
    plain = AESGCM(_encryption_key()).decrypt(_b64url_decode(nonce_text), _b64url_decode(cipher_text), None)
    return plain.decode("utf-8")


def keyed_hmac(value: str, *, scope: str) -> str:
    plain = (value or "").strip()
    return hmac.new(_hmac_key(), f"{scope}:{plain}".encode("utf-8"), hashlib.sha256).hexdigest()
