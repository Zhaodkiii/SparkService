import logging

from accounts.services.device_service import DeviceService

flow_logger = logging.getLogger("accounts.flow")


class DeviceLinkingService:
    """
    登录成功后：用匿名设备画像补全当前用户的设备行，不改绑匿名行（ACCOUNTS-000002）。
    """

    @staticmethod
    def ensure_user_device_profile_from_anonymous(
        *, user, device_id: str, bundle_id: str, request_id: str
    ) -> None:
        device_id = (device_id or "").strip()
        bundle_id = (bundle_id or "").strip()
        if not device_id or not bundle_id or user is None:
            return
        try:
            DeviceService.ensure_user_device_profile_from_anonymous(
                user=user,
                bundle_id=bundle_id,
                device_id=device_id,
                request_id=request_id,
            )
        except Exception as exc:  # noqa: BLE001
            flow_logger.warning(
                "device.profile.ensure.failed",
                extra={
                    "action": "device.profile.ensure",
                    "request_id": request_id,
                    "bundle_id": bundle_id,
                    "device_id": device_id,
                    "user_id": getattr(user, "id", None),
                    "reason": str(exc),
                },
            )

    @staticmethod
    def try_attach_user_to_trusted_device(*, user, device_id: str, bundle_id: str, request_id: str) -> None:
        """兼容入口；语义同 ensure_user_device_profile_from_anonymous（不改绑匿名行）。"""
        DeviceLinkingService.ensure_user_device_profile_from_anonymous(
            user=user,
            device_id=device_id,
            bundle_id=bundle_id,
            request_id=request_id,
        )
