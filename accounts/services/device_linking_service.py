import logging

from accounts.services.device_service import DeviceService

flow_logger = logging.getLogger("accounts.flow")


class DeviceLinkingService:
    """
    登录成功后：用匿名设备画像补全当前用户的设备行，不改绑匿名行（ACCOUNTS-000002）。
    """

    @staticmethod
    def try_attach_user_to_trusted_device(*, user, device_id: str, bundle_id: str, request_id: str) -> None:
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
                "device.attach.failed",
                extra={
                    "action": "device.attach",
                    "request_id": request_id,
                    "bundle_id": bundle_id,
                    "device_id": device_id,
                    "user_id": getattr(user, "id", None),
                    "reason": str(exc),
                },
            )
