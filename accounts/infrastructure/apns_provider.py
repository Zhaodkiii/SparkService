import time
from pathlib import Path
from typing import Optional

from django.conf import settings

try:
    import jwt  # type: ignore
except Exception:  # pragma: no cover
    jwt = None

try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None


class APNsProvider:
    """APNs HTTP/2 provider (JWT + .p8)."""

    BAD_TOKEN_REASONS = {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}

    @staticmethod
    def _load_private_key() -> Optional[str]:
        path = (getattr(settings, "APNS_AUTH_KEY_PATH", "") or "").strip()
        if not path:
            return None
        key_file = Path(path)
        if not key_file.exists():
            return None
        return key_file.read_text(encoding="utf-8")

    @staticmethod
    def _build_jwt() -> Optional[str]:
        if jwt is None:
            return None
        key_pem = APNsProvider._load_private_key()
        if not key_pem:
            return None

        key_id = (getattr(settings, "APNS_KEY_ID", "") or "").strip()
        team_id = (getattr(settings, "APNS_TEAM_ID", "") or "").strip()
        if not key_id or not team_id:
            return None

        token = jwt.encode(
            {"iss": team_id, "iat": int(time.time())},
            key_pem,
            algorithm="ES256",
            headers={"kid": key_id},
        )
        return token if isinstance(token, str) else token.decode("utf-8")

    @staticmethod
    def _base_url() -> str:
        sandbox = bool(getattr(settings, "APNS_USE_SANDBOX", True))
        return "https://api.sandbox.push.apple.com" if sandbox else "https://api.push.apple.com"

    @staticmethod
    def send(*, device_token: str, title: str, body: str, payload: Optional[dict] = None, topic: str = "") -> tuple[bool, str, str]:
        """
        Returns:
            (ok, reason, apns_id)
        """
        if httpx is None:
            return False, "httpx_not_installed", ""

        auth = APNsProvider._build_jwt()
        if not auth:
            return False, "apns_jwt_unavailable", ""

        final_topic = (topic or getattr(settings, "APNS_TOPIC", "") or "").strip()
        if not final_topic:
            return False, "apns_topic_missing", ""

        token = (device_token or "").strip()
        if not token:
            return False, "device_token_missing", ""

        data = {
            "aps": {
                "alert": {
                    "title": title or "",
                    "body": body or "",
                },
                "sound": "default",
            }
        }
        if payload:
            for k, v in payload.items():
                if k != "aps":
                    data[k] = v

        url = f"{APNsProvider._base_url()}/3/device/{token}"
        try:
            with httpx.Client(http2=True, timeout=10.0) as client:
                resp = client.post(
                    url,
                    json=data,
                    headers={
                        "authorization": f"bearer {auth}",
                        "apns-topic": final_topic,
                        "apns-push-type": "alert",
                        "apns-priority": "10",
                    },
                )
        except Exception as exc:  # noqa: BLE001
            return False, f"request_error:{exc}", ""

        apns_id = (resp.headers.get("apns-id") or "").strip()
        if resp.status_code == 200:
            return True, "", apns_id

        reason = ""
        try:
            body_json = resp.json()
            reason = (body_json or {}).get("reason", "") or ""
        except Exception:  # noqa: BLE001
            reason = ""
        if not reason:
            reason = resp.text.strip() or f"http_{resp.status_code}"
        return False, reason, apns_id
