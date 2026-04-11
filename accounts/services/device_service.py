from typing import Any

from common.exceptions import APIError
from accounts.models import TrustedDevice


def _s(data: dict, key: str, default: str = "") -> str:
    v = data.get(key)
    if v is None:
        return default
    return str(v).strip()


def _b(data: dict, key: str, default: bool = False) -> bool:
    v = data.get(key, default)
    if isinstance(v, bool):
        return v
    if v in (None, "", 0):
        return False
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "y", "on")


def _f(data: dict, key: str) -> float | None:
    v = data.get(key)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class DeviceService:
    @staticmethod
    def register_device(
        *,
        user,
        data: dict[str, Any],
        explicit_keys: set[str],
        request_id: str,
    ) -> dict[str, Any]:
        """
        Upsert TrustedDevice by (bundle_id, device_id).
        - user: authenticated user or None (anonymous); body user_id is ignored.
        - Anonymous updates must not clear an existing user link.
        - explicit_keys: keys present on the raw JSON body. Used so omitted ``push_token`` /
          ``notifications_enabled`` do not wipe existing DB values on partial updates (e.g. permission-only sync).
        """
        device_id = _s(data, "device_id")
        bundle_id = _s(data, "bundle_id") or _s(data, "bundle_identifier")
        if not device_id:
            raise APIError("device_id is required", code=40001, status_code=400)
        if not bundle_id:
            raise APIError("bundle_id or bundle_identifier is required", code=40002, status_code=400)

        patch = {
            "app_version": _s(data, "app_version"),
            "build_version": _s(data, "build_version"),
            "bundle_identifier": _s(data, "bundle_identifier") or bundle_id,
            "platform": _s(data, "platform"),
            "system_version": _s(data, "system_version"),
            "device_model": _s(data, "device_model"),
            "device_model_name": _s(data, "device_model_name"),
            "device_name": _s(data, "device_name"),
            "screen_size": _s(data, "screen_size"),
            "screen_scale": _f(data, "screen_scale"),
            "time_zone": _s(data, "time_zone"),
            "language_code": _s(data, "language_code"),
            "region_code": _s(data, "region_code"),
            "is_simulator": _b(data, "is_simulator", False),
            "request_id": request_id or "",
            "is_revoked": False,
        }
        if "push_token" in explicit_keys:
            patch["push_token"] = _s(data, "push_token")
        if "notifications_enabled" in explicit_keys:
            patch["notifications_enabled"] = _b(data, "notifications_enabled", False)

        obj = TrustedDevice.objects.filter(bundle_id=bundle_id, device_id=device_id).first()
        if obj is None:
            create_kwargs = {
                "bundle_id": bundle_id,
                "device_id": device_id,
                "user": user,
                **patch,
            }
            if "push_token" not in patch:
                create_kwargs["push_token"] = ""
            if "notifications_enabled" not in patch:
                create_kwargs["notifications_enabled"] = False
            obj = TrustedDevice.objects.create(**create_kwargs)
            created = True
        else:
            created = False
            if user is not None:
                obj.user = user
            for k, v in patch.items():
                setattr(obj, k, v)
            obj.save()
        return {
            "id": obj.id,
            "device_id": obj.device_id,
            "bundle_id": obj.bundle_id,
            "created": created,
        }

    @staticmethod
    def register_trusted_device(*, user, device_id: str, bundle_id: str, nickname: str, request_id: str):
        """Legacy narrow payload (authenticated clients)."""
        body = {
            "device_id": device_id,
            "bundle_id": bundle_id,
            "device_name": nickname,
        }
        return DeviceService.register_device(
            user=user,
            data=body,
            explicit_keys=set(body.keys()),
            request_id=request_id,
        )
