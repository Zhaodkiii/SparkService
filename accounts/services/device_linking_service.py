from accounts.services.device_service import DeviceService


class DeviceLinkingService:
    """
    登录成功后：用匿名设备画像补全当前用户的设备行，不改绑匿名行（ACCOUNTS-000002）。
    """

    @staticmethod
    def ensure_user_device_profile_from_anonymous(
        *, user, device_id: str, bundle_id: str, request_id: str
    ):
        device_id = (device_id or "").strip()
        bundle_id = (bundle_id or "").strip()
        if not device_id or not bundle_id or user is None:
            return None
        return DeviceService.ensure_user_device_profile_from_anonymous(
            user=user,
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
        )

    @staticmethod
    def try_attach_user_to_trusted_device(*, user, device_id: str, bundle_id: str, request_id: str):
        """兼容入口；语义同 ensure_user_device_profile_from_anonymous（不改绑匿名行）。"""
        return DeviceLinkingService.ensure_user_device_profile_from_anonymous(
            user=user,
            device_id=device_id,
            bundle_id=bundle_id,
            request_id=request_id,
        )
