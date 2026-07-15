import hashlib
import logging
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.utils import IntegrityError, OperationalError, ProgrammingError
from django.utils import timezone

from accounts.models import DeviceLoginCredential
from common.exceptions import APIError

flow_logger = logging.getLogger("accounts.flow")


class DeviceCredentialService:
    MAX_FAILED_ATTEMPTS = 8
    LOCKOUT_MINUTES = 15

    @staticmethod
    def device_id_audit_tail(device_id: str) -> str:
        value = (device_id or "").strip()
        if not value:
            return ""
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return digest[:12]

    @staticmethod
    def _raise_store_unavailable(*, request_id: str, exc: Exception) -> None:
        flow_logger.error(
            "device.credential.store.unavailable",
            extra={
                "action": "auth.device.credential",
                "request_id": request_id,
                "reason": str(exc),
                "error_code": "device_login_store_unavailable",
            },
        )
        raise APIError(
            "device_login_store_unavailable",
            code=50361,
            status_code=503,
            details={
                "reason": "device_login_credential_table_missing_or_unavailable",
                "hint": "run `python manage.py migrate accounts`",
            },
        ) from exc

    @staticmethod
    def verify_or_register(
        *,
        identity_scope: str,
        device_id: str,
        device_secret: str,
        ip_address: str = "",
        request_id: str = "",
        allow_register: bool = True,
    ) -> DeviceLoginCredential:
        """
        锁定 (identity_scope, device_id)：
        - 无凭证：登记 secret_hash
        - 有凭证：校验 secret，更新失败计数 / 锁定 / 最近使用

        失败计数在独立短事务中提交，避免被外层登录事务回滚。
        """
        scope = (identity_scope or "").strip()
        normalized_device_id = (device_id or "").strip()
        secret = (device_secret or "").strip()
        if not scope or not normalized_device_id:
            raise APIError("device_id_required", code=40061, status_code=400)
        if not secret:
            raise APIError("device_secret_required", code=40062, status_code=400)
        if len(normalized_device_id) < 8 or len(normalized_device_id) > 255:
            raise APIError("device_id_invalid", code=40063, status_code=400)

        now = timezone.now()
        audit_tail = DeviceCredentialService.device_id_audit_tail(normalized_device_id)

        try:
            with transaction.atomic():
                credential = (
                    DeviceLoginCredential.objects.select_for_update()
                    .filter(identity_scope=scope, device_id=normalized_device_id)
                    .first()
                )
                if credential is None:
                    if not allow_register:
                        raise APIError("device_credential_not_registered", code=40162, status_code=401)
                    try:
                        credential = DeviceLoginCredential.objects.create(
                            identity_scope=scope,
                            device_id=normalized_device_id,
                            secret_hash=make_password(secret),
                            status=DeviceLoginCredential.Status.ACTIVE,
                            last_used_at=now,
                            last_used_ip=(ip_address or "")[:64],
                        )
                    except IntegrityError:
                        credential = (
                            DeviceLoginCredential.objects.select_for_update()
                            .filter(identity_scope=scope, device_id=normalized_device_id)
                            .first()
                        )
                        if credential is None:
                            raise APIError("device_identity_conflict", code=40961, status_code=409)
                    else:
                        flow_logger.info(
                            "device.credential.registered",
                            extra={
                                "action": "auth.device.credential",
                                "request_id": request_id,
                                "device_id_hash": audit_tail,
                                "identity_scope": scope,
                            },
                        )
                        return credential

                if credential.status != DeviceLoginCredential.Status.ACTIVE:
                    raise APIError("device_credential_invalid", code=40161, status_code=401)

                if credential.locked_until and credential.locked_until > now:
                    raise APIError("device_credential_locked", code=42361, status_code=423)

                if check_password(secret, credential.secret_hash):
                    credential.failed_attempts = 0
                    credential.locked_until = None
                    credential.last_used_at = now
                    credential.last_used_ip = (ip_address or "")[:64]
                    credential.save(
                        update_fields=[
                            "failed_attempts",
                            "locked_until",
                            "last_used_at",
                            "last_used_ip",
                            "updated_at",
                        ]
                    )
                    return credential

                credential_id = credential.id

            # 独立事务提交失败计数，避免外层登录失败回滚防暴力计数。
            with transaction.atomic():
                credential = DeviceLoginCredential.objects.select_for_update().get(pk=credential_id)
                credential.failed_attempts += 1
                update_fields = ["failed_attempts", "updated_at"]
                if credential.failed_attempts >= DeviceCredentialService.MAX_FAILED_ATTEMPTS:
                    credential.locked_until = now + timedelta(
                        minutes=DeviceCredentialService.LOCKOUT_MINUTES
                    )
                    update_fields.append("locked_until")
                credential.save(update_fields=update_fields)
                failed_attempts = credential.failed_attempts

            flow_logger.warning(
                "device.credential.invalid",
                extra={
                    "action": "auth.device.credential",
                    "request_id": request_id,
                    "device_id_hash": audit_tail,
                    "failed_attempts": failed_attempts,
                },
            )
            raise APIError("device_credential_invalid", code=40161, status_code=401)
        except (OperationalError, ProgrammingError) as exc:
            DeviceCredentialService._raise_store_unavailable(request_id=request_id, exc=exc)
