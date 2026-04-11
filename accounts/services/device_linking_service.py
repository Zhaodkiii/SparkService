import logging

from accounts.models import TrustedDevice

flow_logger = logging.getLogger("accounts.flow")


class DeviceLinkingService:
    """
    登录成功后尝试把匿名登记的 TrustedDevice 关联到当前用户；失败只打日志。
    """

    @staticmethod
    def try_attach_user_to_trusted_device(*, user, device_id: str, bundle_id: str, request_id: str) -> None:
        device_id = (device_id or "").strip()
        bundle_id = (bundle_id or "").strip()
        if not device_id or not bundle_id or user is None:
            return
        try:
            row = TrustedDevice.objects.filter(bundle_id=bundle_id, device_id=device_id).first()
            if row is None:
                flow_logger.info(
                    "device.attach.skip_no_row",
                    extra={
                        "action": "device.attach",
                        "request_id": request_id,
                        "bundle_id": bundle_id,
                        "device_id": device_id,
                        "user_id": user.id,
                    },
                )
                return
            if row.user_id is None:
                row.user = user
                row.save(update_fields=["user"])
                flow_logger.info(
                    "device.attach.ok",
                    extra={
                        "action": "device.attach",
                        "request_id": request_id,
                        "bundle_id": bundle_id,
                        "device_id": device_id,
                        "user_id": user.id,
                    },
                )
                return
            if row.user_id != user.id:
                flow_logger.warning(
                    "device.attach.conflict_existing_user",
                    extra={
                        "action": "device.attach",
                        "request_id": request_id,
                        "bundle_id": bundle_id,
                        "device_id": device_id,
                        "expected_user_id": user.id,
                        "existing_user_id": row.user_id,
                    },
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
