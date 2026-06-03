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


_PROFILE_STRING_FIELDS = (
    "app_version",
    "build_version",
    "bundle_identifier",
    "platform",
    "system_version",
    "device_model",
    "device_model_name",
    "device_name",
    "screen_size",
    "time_zone",
    "language_code",
    "region_code",
    "country_code",
)

_PROFILE_COPY_FIELDS = _PROFILE_STRING_FIELDS + ("screen_scale", "is_simulator")

_ALWAYS_APPLY_PATCH_KEYS = frozenset({"request_id", "is_revoked"})


class DeviceService:
    @staticmethod
    def _build_patch(
        *,
        data: dict[str, Any],
        explicit_keys: set[str],
        request_id: str,
        bundle_id: str,
    ) -> dict[str, Any]:
        """仅收集请求体显式携带的字段；未在 explicit_keys 中的画像字段不参与 patch。"""
        patch: dict[str, Any] = {
            "request_id": request_id or "",
            "is_revoked": False,
        }

        for field in _PROFILE_STRING_FIELDS:
            if field in explicit_keys:
                if field == "bundle_identifier":
                    patch[field] = _s(data, "bundle_identifier") or bundle_id
                else:
                    patch[field] = _s(data, field)

        if "screen_scale" in explicit_keys:
            patch["screen_scale"] = _f(data, "screen_scale")
        if "is_simulator" in explicit_keys:
            patch["is_simulator"] = _b(data, "is_simulator", False)
        if "push_token" in explicit_keys:
            raw_push = data.get("push_token")
            if raw_push is not None:
                patch["push_token"] = _s(data, "push_token")
        if "notifications_enabled" in explicit_keys:
            patch["notifications_enabled"] = _b(data, "notifications_enabled", False)

        return patch

    @staticmethod
    def _apply_patch_to_row(
        *,
        row: TrustedDevice,
        patch: dict[str, Any],
        explicit_keys: set[str],
    ) -> None:
        """应用 patch：画像字符串字段仅非空时写入，避免空串冲掉匿名补全值。"""
        for key, value in patch.items():
            if key in _ALWAYS_APPLY_PATCH_KEYS:
                setattr(row, key, value)
                continue
            if key not in explicit_keys:
                continue
            if key == "push_token":
                setattr(row, "push_token", value)
                continue
            if key == "notifications_enabled":
                setattr(row, "notifications_enabled", value)
                continue
            if key == "screen_scale":
                setattr(row, "screen_scale", value)
                continue
            if key == "is_simulator":
                setattr(row, "is_simulator", value)
                continue
            if key in _PROFILE_STRING_FIELDS and value not in (None, ""):
                setattr(row, key, value)

    @staticmethod
    def _anonymous_row(*, bundle_id: str, device_id: str) -> TrustedDevice | None:
        return TrustedDevice.objects.filter(
            bundle_id=bundle_id,
            device_id=device_id,
            user__isnull=True,
        ).first()

    @staticmethod
    def _seed_from_anonymous(*, bundle_id: str, device_id: str) -> dict[str, Any]:
        anon = DeviceService._anonymous_row(bundle_id=bundle_id, device_id=device_id)
        if anon is None:
            return {}
        seed = {
            field: getattr(anon, field)
            for field in _PROFILE_COPY_FIELDS
            if getattr(anon, field, None) not in (None, "")
        }
        if anon.push_token:
            seed["push_token"] = anon.push_token
        if anon.notifications_enabled:
            seed["notifications_enabled"] = anon.notifications_enabled
        return seed

    @staticmethod
    def _merge_anonymous_profile_into_user_row(
        *,
        user_row: TrustedDevice,
        anon: TrustedDevice,
        explicit_keys: set[str],
    ) -> None:
        """用匿名行画像覆盖/补全用户行；匿名行保持 user=NULL。"""
        for field in _PROFILE_COPY_FIELDS:
            value = getattr(anon, field, None)
            if value not in (None, ""):
                setattr(user_row, field, value)
        if "push_token" not in explicit_keys and anon.push_token:
            user_row.push_token = anon.push_token
        if "notifications_enabled" not in explicit_keys:
            user_row.notifications_enabled = anon.notifications_enabled

    @staticmethod
    def ensure_user_device_profile_from_anonymous(
        *,
        user,
        bundle_id: str,
        device_id: str,
        request_id: str = "",
    ) -> TrustedDevice:
        bundle_id = (bundle_id or "").strip()
        device_id = (device_id or "").strip()
        if not bundle_id or not device_id:
            raise APIError("bundle_id and device_id are required", code=40002, status_code=400)

        anon = DeviceService._anonymous_row(bundle_id=bundle_id, device_id=device_id)
        user_row = TrustedDevice.objects.filter(
            bundle_id=bundle_id,
            device_id=device_id,
            user=user,
        ).first()

        if user_row is None:
            seed = DeviceService._seed_from_anonymous(bundle_id=bundle_id, device_id=device_id)
            user_row = TrustedDevice.objects.create(
                bundle_id=bundle_id,
                device_id=device_id,
                user=user,
                push_token=seed.get("push_token", ""),
                notifications_enabled=seed.get("notifications_enabled", False),
                **{k: v for k, v in seed.items() if k not in ("push_token", "notifications_enabled")},
            )
            return user_row

        if anon is not None:
            DeviceService._merge_anonymous_profile_into_user_row(
                user_row=user_row,
                anon=anon,
                explicit_keys=set(),
            )
            user_row.request_id = request_id or user_row.request_id
            user_row.save()
        return user_row

    @staticmethod
    def register_device(
        *,
        user,
        data: dict[str, Any],
        explicit_keys: set[str],
        request_id: str,
    ) -> dict[str, Any]:
        """
        Upsert TrustedDevice by (bundle_id, device_id, user).
        - user=None: only touch anonymous row; never overwrite user-bound rows.
        - user set: only touch that user's row; merge anonymous then apply explicit patch.
        """
        device_id = _s(data, "device_id")
        bundle_id = _s(data, "bundle_id") or _s(data, "bundle_identifier")
        if not device_id:
            raise APIError("device_id is required", code=40001, status_code=400)
        if not bundle_id:
            raise APIError("bundle_id or bundle_identifier is required", code=40002, status_code=400)

        patch = DeviceService._build_patch(
            data=data,
            explicit_keys=explicit_keys,
            request_id=request_id,
            bundle_id=bundle_id,
        )

        if user is None:
            obj = TrustedDevice.objects.filter(
                bundle_id=bundle_id,
                device_id=device_id,
                user__isnull=True,
            ).first()
            if obj is None:
                obj = TrustedDevice.objects.create(
                    bundle_id=bundle_id,
                    device_id=device_id,
                    user=None,
                    push_token="",
                    notifications_enabled=False,
                )
                created = True
            else:
                created = False
            DeviceService._apply_patch_to_row(row=obj, patch=patch, explicit_keys=explicit_keys)
            obj.save()
        else:
            obj = TrustedDevice.objects.filter(
                bundle_id=bundle_id,
                device_id=device_id,
                user=user,
            ).first()
            if obj is None:
                seed = DeviceService._seed_from_anonymous(bundle_id=bundle_id, device_id=device_id)
                obj = TrustedDevice.objects.create(
                    bundle_id=bundle_id,
                    device_id=device_id,
                    user=user,
                    push_token=seed.get("push_token", ""),
                    notifications_enabled=seed.get("notifications_enabled", False),
                    **{k: v for k, v in seed.items() if k not in ("push_token", "notifications_enabled")},
                )
                created = True
            else:
                created = False
                anon = DeviceService._anonymous_row(bundle_id=bundle_id, device_id=device_id)
                if anon is not None:
                    DeviceService._merge_anonymous_profile_into_user_row(
                        user_row=obj,
                        anon=anon,
                        explicit_keys=explicit_keys,
                    )
            DeviceService._apply_patch_to_row(row=obj, patch=patch, explicit_keys=explicit_keys)
            obj.save()

        return {
            "id": obj.id,
            "device_id": obj.device_id,
            "bundle_id": obj.bundle_id,
            "created": created,
        }
