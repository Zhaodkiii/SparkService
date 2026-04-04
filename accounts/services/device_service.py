from django.utils import timezone

from common.exceptions import APIError
from accounts.models import TrustedDevice


class DeviceService:
    @staticmethod
    def register_trusted_device(*, user, device_id: str, bundle_id: str, nickname: str, request_id: str):
        device_id = (device_id or "").strip()
        if not device_id:
            raise APIError("device_id is required", code=40001, status_code=400)

        obj, _ = TrustedDevice.objects.get_or_create(
            user=user,
            device_id=device_id,
            defaults={
                "bundle_id": bundle_id or "",
                "nickname": nickname or "",
                "request_id": request_id or "",
            },
        )
        obj.bundle_id = bundle_id or obj.bundle_id
        obj.nickname = nickname or obj.nickname
        obj.is_revoked = False
        obj.last_seen_at = timezone.now()
        obj.request_id = request_id or obj.request_id
        obj.save(update_fields=["bundle_id", "nickname", "is_revoked", "last_seen_at", "request_id"])
        return {"device_id": obj.device_id, "bundle_id": obj.bundle_id}

