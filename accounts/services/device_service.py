from typing import Any

from django.contrib.auth import get_user_model

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


def _parse_unsigned_hint_user_id(data: dict[str, Any], explicit_keys: set[str]) -> int | None:
    """未登录登记时 body.user_id 仅作辅助定位，非鉴权凭证。"""
    if "user_id" not in explicit_keys:
        return None
    raw = data.get("user_id")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
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

_ALWAYS_APPLY_PATCH_KEYS = frozenset({"request_id"})


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
        reactivate: bool = False,
    ) -> None:
        """应用 patch：画像字符串字段仅非空时写入；reactivate 时置 is_revoked=false。"""
        if reactivate:
            row.is_revoked = False

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
    def _user_row(*, bundle_id: str, device_id: str, user) -> TrustedDevice | None:
        return TrustedDevice.objects.filter(
            bundle_id=bundle_id,
            device_id=device_id,
            user=user,
        ).first()

    @staticmethod
    def _copy_profile_fields(*, source: TrustedDevice, target: TrustedDevice) -> None:
        for field in _PROFILE_COPY_FIELDS:
            value = getattr(source, field, None)
            if value not in (None, ""):
                setattr(target, field, value)
        if source.push_token:
            target.push_token = source.push_token
        target.notifications_enabled = source.notifications_enabled

    @staticmethod
    def _resolve_unsigned_register_row(
        *,
        bundle_id: str,
        device_id: str,
        data: dict[str, Any],
        explicit_keys: set[str],
    ) -> TrustedDevice | None:
        """
        未登录登记目标行：仅 body.user_id 命中已有用户行时更新该行；否则匿名行。
        不允许凭 body 创建任意用户设备行。
        """
        User = get_user_model()
        hinted_user_id = _parse_unsigned_hint_user_id(data, explicit_keys)
        if hinted_user_id is not None and User.objects.filter(pk=hinted_user_id).exists():
            hinted = TrustedDevice.objects.filter(
                bundle_id=bundle_id,
                device_id=device_id,
                user_id=hinted_user_id,
            ).first()
            if hinted is not None:
                return hinted

        return DeviceService._anonymous_row(bundle_id=bundle_id, device_id=device_id)

    @staticmethod
    def _upgrade_anonymous_row_to_user(
        *,
        anon: TrustedDevice,
        user,
        patch: dict[str, Any],
        explicit_keys: set[str],
    ) -> TrustedDevice:
        """匿名行升级为当前用户行（ACCOUNTS-000003）。"""
        anon.user = user
        DeviceService._apply_patch_to_row(
            row=anon,
            patch=patch,
            explicit_keys=explicit_keys,
            reactivate=True,
        )
        anon.save()
        return anon

    @staticmethod
    def _absorb_anonymous_into_user_row(
        *,
        anon: TrustedDevice,
        user_row: TrustedDevice,
    ) -> None:
        DeviceService._copy_profile_fields(source=anon, target=user_row)
        anon.delete()

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
        user_row = DeviceService._user_row(bundle_id=bundle_id, device_id=device_id, user=user)

        if user_row is not None:
            if anon is not None:
                DeviceService._absorb_anonymous_into_user_row(anon=anon, user_row=user_row)
            user_row.is_revoked = False
            user_row.request_id = request_id or user_row.request_id
            user_row.save()
            return user_row

        if anon is not None:
            anon.user = user
            anon.is_revoked = False
            anon.request_id = request_id or anon.request_id
            anon.save()
            return anon

        return TrustedDevice.objects.create(
            bundle_id=bundle_id,
            device_id=device_id,
            user=user,
            is_revoked=False,
            request_id=request_id or "",
        )

    @staticmethod
    def register_device(
        *,
        user,
        data: dict[str, Any],
        explicit_keys: set[str],
        request_id: str,
    ) -> dict[str, Any]:
        """
        Upsert TrustedDevice（ACCOUNTS-000003）。
        - user=None：更新 revoked 用户行或创建唯一匿名行；不凭 body 创建任意用户行。
        - user set：升级匿名行或更新当前用户行，is_revoked=false。
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
            obj = DeviceService._resolve_unsigned_register_row(
                bundle_id=bundle_id,
                device_id=device_id,
                data=data,
                explicit_keys=explicit_keys,
            )
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
            DeviceService._apply_patch_to_row(
                row=obj,
                patch=patch,
                explicit_keys=explicit_keys,
                reactivate=False,
            )
            obj.save()
        else:
            user_row = DeviceService._user_row(bundle_id=bundle_id, device_id=device_id, user=user)
            anon = DeviceService._anonymous_row(bundle_id=bundle_id, device_id=device_id)

            if user_row is not None:
                created = False
                if anon is not None:
                    DeviceService._absorb_anonymous_into_user_row(anon=anon, user_row=user_row)
                obj = user_row
            elif anon is not None:
                created = True
                obj = DeviceService._upgrade_anonymous_row_to_user(
                    anon=anon,
                    user=user,
                    patch=patch,
                    explicit_keys=explicit_keys,
                )
                return {
                    "id": obj.id,
                    "device_id": obj.device_id,
                    "bundle_id": obj.bundle_id,
                    "created": created,
                }
            else:
                created = True
                obj = TrustedDevice.objects.create(
                    bundle_id=bundle_id,
                    device_id=device_id,
                    user=user,
                    push_token="",
                    notifications_enabled=False,
                    is_revoked=False,
                )

            DeviceService._apply_patch_to_row(
                row=obj,
                patch=patch,
                explicit_keys=explicit_keys,
                reactivate=True,
            )
            obj.save()

        return {
            "id": obj.id,
            "device_id": obj.device_id,
            "bundle_id": obj.bundle_id,
            "created": created,
        }
