import logging
import uuid
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections, router, transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import (
    AccessDenyEntry,
    AccessDenyHit,
    AccountDeviceSession,
    LoginAudit,
    SocialIdentity,
    TrustedDevice,
)
from accounts.services.login_audit_service import LoginAuditService
from accounts.services.phone_number_service import PhoneNumberService
from common.exceptions import APIError

flow_logger = logging.getLogger("accounts.flow")

PUBLIC_BAN_REASON = "您的账号因违规行为已触犯用户协议，已被系统永久禁止登录。"
ACCOUNT_BANNED_SCENE = "account.lifecycle.login_banned"


class AccessControlService:
    @staticmethod
    def normalize_device_id(value: str) -> str:
        return (value or "").strip()

    @staticmethod
    def normalize_email(value: str) -> str:
        return (value or "").strip().lower()

    @staticmethod
    def normalize_phone(value: str) -> str:
        return PhoneNumberService.normalize_e164(value)

    @staticmethod
    def _active_queryset():
        now = timezone.now()
        return AccessDenyEntry.objects.filter(revoked_at__isnull=True).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )

    @staticmethod
    def _build_candidate_pairs(
        *,
        user_id: int | None = None,
        email: str = "",
        phone: str = "",
    ) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        if user_id:
            pairs.append((AccessDenyEntry.Dimension.USER_ID, str(int(user_id))))
        normalized_email = AccessControlService.normalize_email(email)
        if normalized_email:
            pairs.append((AccessDenyEntry.Dimension.EMAIL, normalized_email))
        if (phone or "").strip():
            try:
                pairs.append((AccessDenyEntry.Dimension.PHONE, AccessControlService.normalize_phone(phone)))
            except APIError:
                pass
        return pairs

    @staticmethod
    def find_active_hit(*, user_id: int | None = None, email: str = "", phone: str = "") -> AccessDenyEntry | None:
        pairs = AccessControlService._build_candidate_pairs(user_id=user_id, email=email, phone=phone)
        if not pairs:
            return None
        query = Q()
        for dimension, value in pairs:
            query |= Q(dimension=dimension, dimension_value=value)
        return AccessControlService._active_queryset().filter(query).order_by("-created_at").first()

    @staticmethod
    def _record_hit(
        *,
        hit: AccessDenyEntry,
        action: str,
        provider: str,
        user_id: int | None = None,
        email: str = "",
        phone: str = "",
        bundle_id: str = "",
        device_id: str = "",
        request_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
    ) -> None:
        attempted_phone = ""
        if (phone or "").strip():
            try:
                attempted_phone = AccessControlService.normalize_phone(phone)
            except APIError:
                attempted_phone = (phone or "").strip()
        try:
            AccessControlService._insert_hit_autocommit(
                deny_entry_id=hit.id,
                action=action,
                hit_dimension=hit.dimension,
                hit_value=hit.dimension_value,
                reason_code=hit.reason_code or "account_banned",
                provider=provider,
                attempted_user_id=user_id,
                attempted_email=AccessControlService.normalize_email(email),
                attempted_phone=attempted_phone,
                device_id=AccessControlService.normalize_device_id(device_id),
                bundle_id=(bundle_id or "").strip(),
                ip_address=(ip_address or "").strip()[:64],
                user_agent=(user_agent or "")[:2000],
                request_id=(request_id or "").strip()[:64],
                created_at=timezone.now(),
            )
        except Exception as exc:
            flow_logger.warning(
                "access.deny_hit.write_failed",
                extra={
                    "action": "access.deny_hit.write_failed",
                    "request_id": request_id,
                    "deny_entry_id": hit.id,
                    "reason": str(exc),
                },
            )

    @staticmethod
    def _insert_hit_autocommit(**field_values: Any) -> None:
        """Insert AccessDenyHit on a new connection so login atomic rollback cannot undo it."""
        instance = AccessDenyHit(**field_values)
        alias = router.db_for_write(AccessDenyHit)
        extra = connections.create_connection(alias)
        extra.set_autocommit(True)
        try:
            columns: list[str] = []
            values: list[Any] = []
            for field in AccessDenyHit._meta.local_concrete_fields:
                if field.primary_key and getattr(field, "auto_created", False):
                    continue
                attname = field.attname
                if attname not in field_values and not hasattr(instance, attname):
                    continue
                raw = getattr(instance, attname)
                columns.append(extra.ops.quote_name(field.column))
                values.append(field.get_db_prep_save(raw, connection=extra))
            table = extra.ops.quote_name(AccessDenyHit._meta.db_table)
            placeholders = ", ".join(["%s"] * len(columns))
            sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
            with extra.cursor() as cursor:
                cursor.execute(sql, values)
        finally:
            extra.close()

    @staticmethod
    def check(
        *,
        user_id: int | None = None,
        email: str = "",
        phone: str = "",
        provider: str = LoginAudit.LoginProvider.PASSWORD,
        bundle_id: str = "",
        device_id: str = "",
        request_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
        action: str = AccessDenyHit.Action.LOGIN,
    ) -> None:
        hit = AccessControlService.find_active_hit(user_id=user_id, email=email, phone=phone)
        if hit is None:
            return
        AccessControlService._record_hit(
            hit=hit,
            action=action,
            provider=provider,
            user_id=user_id,
            email=email,
            phone=phone,
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        LoginAuditService.write_failure(
            provider=provider,
            bundle_id=bundle_id or "",
            device_id=device_id or "",
            request_id=request_id or "",
            ip_address=ip_address or "",
            user_agent=user_agent or "",
            status_code=403,
            error_code=40371,
            error_message="access_denied",
            raw_claims={
                "failure_stage": "access_denied",
                "deny_entry_id": hit.id,
                "deny_dimension": hit.dimension,
                "reason_code": hit.reason_code,
            },
            user=get_user_model().objects.filter(id=hit.related_user_id).first() if hit.related_user_id else None,
        )
        flow_logger.warning(
            "access.denied",
            extra={
                "action": "access.denied",
                "request_id": request_id,
                "deny_entry_id": hit.id,
                "dimension": hit.dimension,
                "user_id": user_id,
            },
        )
        raise APIError(
            "access_denied",
            code=40371,
            status_code=403,
            details={
                "reason_code": hit.reason_code or "account_banned",
                "public_reason": PUBLIC_BAN_REASON,
            },
        )

    @staticmethod
    def find_active_device_hit(*, device_id: str) -> AccessDenyEntry | None:
        normalized = AccessControlService.normalize_device_id(device_id)
        if not normalized:
            return None
        return (
            AccessControlService._active_queryset()
            .filter(
                dimension=AccessDenyEntry.Dimension.DEVICE,
                dimension_value=normalized,
            )
            .order_by("-created_at")
            .first()
        )

    @staticmethod
    def check_device_registration(
        *,
        device_id: str,
        provider: str = LoginAudit.LoginProvider.PASSWORD,
        bundle_id: str = "",
        request_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
        action: str = AccessDenyHit.Action.REGISTER,
        phone: str = "",
    ) -> None:
        hit = AccessControlService.find_active_device_hit(device_id=device_id)
        if hit is None:
            return
        action_key = action or AccessDenyHit.Action.REGISTER
        is_otp = action_key == AccessDenyHit.Action.OTP_REQUEST
        failure_stage = "device_otp_denied" if is_otp else "device_registration_denied"
        log_action = "access.device_otp.denied" if is_otp else "access.device_registration.denied"
        AccessControlService._record_hit(
            hit=hit,
            action=action_key,
            provider=provider,
            device_id=device_id,
            bundle_id=bundle_id,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            phone=phone,
        )
        LoginAuditService.write_failure(
            provider=provider,
            bundle_id=bundle_id or "",
            device_id=AccessControlService.normalize_device_id(device_id),
            request_id=request_id or "",
            ip_address=ip_address or "",
            user_agent=user_agent or "",
            status_code=403,
            error_code=40371,
            error_message="access_denied",
            raw_claims={
                "failure_stage": failure_stage,
                "deny_entry_id": hit.id,
                "deny_dimension": hit.dimension,
                "reason_code": hit.reason_code,
            },
            user=get_user_model().objects.filter(id=hit.related_user_id).first() if hit.related_user_id else None,
        )
        flow_logger.warning(
            log_action,
            extra={
                "action": log_action,
                "request_id": request_id,
                "deny_entry_id": hit.id,
                "device_id": AccessControlService.normalize_device_id(device_id),
            },
        )
        raise APIError(
            "access_denied",
            code=40371,
            status_code=403,
            details={
                "reason_code": hit.reason_code or "account_banned",
                "public_reason": PUBLIC_BAN_REASON,
            },
        )

    @staticmethod
    def _collect_user_identities(*, user) -> dict[str, set[str]]:
        emails: set[str] = set()
        phones: set[str] = set()
        email = AccessControlService.normalize_email(getattr(user, "email", "") or "")
        if email:
            emails.add(email)
        for provider, uid in SocialIdentity.objects.filter(user=user).values_list("provider", "provider_uid"):
            if provider == SocialIdentity.Provider.EMAIL and uid:
                emails.add(AccessControlService.normalize_email(uid))
            elif provider == SocialIdentity.Provider.PHONE and uid:
                phones.add(uid.strip())
        return {"emails": emails, "phones": phones}

    @staticmethod
    def _collect_user_device_ids(*, user) -> set[str]:
        device_ids: set[str] = set()
        for device_id in TrustedDevice.objects.filter(user=user).values_list("device_id", flat=True):
            normalized = AccessControlService.normalize_device_id(device_id)
            if normalized:
                device_ids.add(normalized)
        for device_id in AccountDeviceSession.objects.filter(user=user).values_list("device_id", flat=True):
            normalized = AccessControlService.normalize_device_id(device_id)
            if normalized:
                device_ids.add(normalized)
        for provider_uid in SocialIdentity.objects.filter(
            user=user,
            provider=SocialIdentity.Provider.DEVICE,
        ).values_list("provider_uid", flat=True):
            normalized = AccessControlService.normalize_device_id(provider_uid)
            if normalized:
                device_ids.add(normalized)
        for device_id in (
            LoginAudit.objects.filter(user=user, outcome=LoginAudit.LoginOutcome.SUCCESS)
            .exclude(device_id="")
            .values_list("device_id", flat=True)
            .distinct()
        ):
            normalized = AccessControlService.normalize_device_id(device_id)
            if normalized:
                device_ids.add(normalized)
        return device_ids

    @staticmethod
    def _phone_for_user(user) -> str:
        identity = SocialIdentity.objects.filter(user=user, provider=SocialIdentity.Provider.PHONE).first()
        return (identity.provider_uid if identity else "").strip()

    @staticmethod
    def _ensure_entry(
        *,
        dimension: str,
        dimension_value: str,
        source: str,
        reason_note: str = "",
        related_user_id: int | None = None,
        created_by_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[AccessDenyEntry, bool]:
        existing = AccessControlService._active_queryset().filter(
            dimension=dimension,
            dimension_value=dimension_value,
        ).first()
        if existing is not None:
            return existing, False
        entry = AccessDenyEntry.objects.create(
            dimension=dimension,
            dimension_value=dimension_value,
            reason_code="account_banned",
            reason_note=(reason_note or "").strip(),
            source=source,
            related_user_id=related_user_id,
            created_by_id=created_by_id,
            metadata=metadata or {},
        )
        return entry, True

    @staticmethod
    def _disable_user_sessions(*, user, request_id: str = "") -> None:
        from accounts.services.deactivation_service import DeactivationService
        from accounts.services.device_login_service import DeviceLoginService

        user.is_active = False
        user.save(update_fields=["is_active"])
        DeviceLoginService.revoke_active_sessions_for_user(user=user, reason="account_banned")
        DeactivationService._blacklist_refresh_tokens(user=user)
        flow_logger.info(
            "access.ban.user_disabled",
            extra={"action": "access.ban", "user_id": user.id, "request_id": request_id},
        )

    @staticmethod
    def _send_ban_sms(*, phone_number: str, user_id: int | None, request_id: str) -> dict[str, Any]:
        phone = (phone_number or "").strip()
        if not phone:
            return {"sms_status": "skipped", "sms_reason": "phone_not_bound"}
        from notification_center.services import NotificationCenterService

        ok, reason, provider_message_id = NotificationCenterService.send_account_banned_sms(
            phone_number=phone,
            user_id=user_id,
            request_id=request_id or uuid.uuid4().hex,
        )
        return {
            "sms_status": "sent" if ok else "failed",
            "sms_reason": reason or "",
            "provider_message_id": provider_message_id or "",
        }

    @staticmethod
    def _find_bannable_users_by_phone(*, normalized_phone: str):
        User = get_user_model()
        user_ids = list(
            SocialIdentity.objects.filter(
                provider=SocialIdentity.Provider.PHONE,
                provider_uid=normalized_phone,
            ).values_list("user_id", flat=True).distinct()
        )
        users = []
        for user_id in user_ids:
            user = User.objects.filter(id=user_id).first()
            if user is None:
                continue
            if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
                continue
            users.append(user)
        return users

    @staticmethod
    def _find_bannable_users_by_email(*, normalized_email: str):
        User = get_user_model()
        user_ids = set(
            SocialIdentity.objects.filter(
                provider=SocialIdentity.Provider.EMAIL,
                provider_uid=normalized_email,
            ).values_list("user_id", flat=True)
        )
        user_ids.update(User.objects.filter(email__iexact=normalized_email).values_list("id", flat=True))
        users = []
        for user_id in user_ids:
            user = User.objects.filter(id=user_id).first()
            if user is None:
                continue
            if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
                continue
            users.append(user)
        return users

    @staticmethod
    @transaction.atomic
    def ban_user(
        *,
        user,
        reason_note: str = "",
        created_by_id: int | None = None,
        request_id: str = "",
        send_sms: bool = True,
        expand_identities: bool = False,
    ) -> dict[str, Any]:
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            raise APIError("cannot_ban_admin_user", code=40072, status_code=400)

        user_entry, user_created = AccessControlService._ensure_entry(
            dimension=AccessDenyEntry.Dimension.USER_ID,
            dimension_value=str(user.id),
            source=AccessDenyEntry.Source.ADMIN,
            reason_note=reason_note,
            related_user_id=user.id,
            created_by_id=created_by_id,
        )
        expanded_entries: list[int] = []
        if expand_identities:
            identities = AccessControlService._collect_user_identities(user=user)
            for email in identities["emails"]:
                entry, created = AccessControlService._ensure_entry(
                    dimension=AccessDenyEntry.Dimension.EMAIL,
                    dimension_value=email,
                    source=AccessDenyEntry.Source.AUTO_EXPAND,
                    related_user_id=user.id,
                    created_by_id=created_by_id,
                )
                if created:
                    expanded_entries.append(entry.id)
            for phone in identities["phones"]:
                entry, created = AccessControlService._ensure_entry(
                    dimension=AccessDenyEntry.Dimension.PHONE,
                    dimension_value=phone,
                    source=AccessDenyEntry.Source.AUTO_EXPAND,
                    related_user_id=user.id,
                    created_by_id=created_by_id,
                )
                if created:
                    expanded_entries.append(entry.id)

        for device_id in AccessControlService._collect_user_device_ids(user=user):
            entry, created = AccessControlService._ensure_entry(
                dimension=AccessDenyEntry.Dimension.DEVICE,
                dimension_value=device_id,
                source=AccessDenyEntry.Source.AUTO_EXPAND,
                related_user_id=user.id,
                created_by_id=created_by_id,
            )
            if created:
                expanded_entries.append(entry.id)

        AccessControlService._disable_user_sessions(user=user, request_id=request_id)
        sms_result = {"sms_status": "skipped", "sms_reason": "send_disabled"}
        if send_sms:
            sms_result = AccessControlService._send_ban_sms(
                phone_number=AccessControlService._phone_for_user(user),
                user_id=user.id,
                request_id=request_id,
            )
            user_entry.metadata = {**(user_entry.metadata or {}), **sms_result}
            user_entry.save(update_fields=["metadata", "updated_at"])

        return {
            "entry_id": user_entry.id,
            "user_id": user.id,
            "created": user_created,
            "expanded_entry_ids": expanded_entries,
            **sms_result,
        }

    @staticmethod
    @transaction.atomic
    def ban_phone(
        *,
        phone_number: str,
        reason_note: str = "",
        created_by_id: int | None = None,
        request_id: str = "",
    ) -> dict[str, Any]:
        normalized_phone = AccessControlService.normalize_phone(phone_number)
        bannable_users = AccessControlService._find_bannable_users_by_phone(normalized_phone=normalized_phone)
        if bannable_users:
            user_results: list[dict[str, Any]] = []
            for index, user in enumerate(bannable_users):
                user_results.append(
                    AccessControlService.ban_user(
                        user=user,
                        reason_note=reason_note,
                        created_by_id=created_by_id,
                        request_id=request_id,
                        send_sms=index == 0,
                        expand_identities=False,
                    )
                )
            primary = user_results[0]
            return {
                "entry_id": primary["entry_id"],
                "phone": normalized_phone,
                "created": primary["created"],
                "matched_user": True,
                "linked_users": user_results,
                "sms_status": primary.get("sms_status", "skipped"),
                "sms_reason": primary.get("sms_reason", ""),
                "provider_message_id": primary.get("provider_message_id", ""),
            }

        phone_entry, phone_created = AccessControlService._ensure_entry(
            dimension=AccessDenyEntry.Dimension.PHONE,
            dimension_value=normalized_phone,
            source=AccessDenyEntry.Source.ADMIN,
            reason_note=reason_note,
            created_by_id=created_by_id,
        )
        sms_result = AccessControlService._send_ban_sms(
            phone_number=normalized_phone,
            user_id=None,
            request_id=request_id,
        )
        phone_entry.metadata = {**(phone_entry.metadata or {}), **sms_result, "matched_user": False}
        phone_entry.save(update_fields=["metadata", "updated_at"])

        return {
            "entry_id": phone_entry.id,
            "phone": normalized_phone,
            "created": phone_created,
            "matched_user": False,
            "linked_users": [],
            **sms_result,
        }

    @staticmethod
    @transaction.atomic
    def ban_email(
        *,
        email: str,
        reason_note: str = "",
        created_by_id: int | None = None,
        request_id: str = "",
    ) -> dict[str, Any]:
        normalized_email = AccessControlService.normalize_email(email)
        bannable_users = AccessControlService._find_bannable_users_by_email(normalized_email=normalized_email)
        if bannable_users:
            user_results: list[dict[str, Any]] = []
            for index, user in enumerate(bannable_users):
                user_results.append(
                    AccessControlService.ban_user(
                        user=user,
                        reason_note=reason_note,
                        created_by_id=created_by_id,
                        request_id=request_id,
                        send_sms=index == 0,
                        expand_identities=False,
                    )
                )
            primary = user_results[0]
            return {
                "entry_id": primary["entry_id"],
                "email": normalized_email,
                "created": primary["created"],
                "matched_user": True,
                "linked_users": user_results,
                "sms_status": primary.get("sms_status", "skipped"),
                "sms_reason": primary.get("sms_reason", ""),
                "provider_message_id": primary.get("provider_message_id", ""),
            }

        email_entry, email_created = AccessControlService._ensure_entry(
            dimension=AccessDenyEntry.Dimension.EMAIL,
            dimension_value=normalized_email,
            source=AccessDenyEntry.Source.ADMIN,
            reason_note=reason_note,
            created_by_id=created_by_id,
        )
        email_entry.metadata = {"matched_user": False, "linked_users": []}
        email_entry.save(update_fields=["metadata", "updated_at"])
        return {
            "entry_id": email_entry.id,
            "email": normalized_email,
            "created": email_created,
            "matched_user": False,
            "linked_users": [],
            "sms_status": "skipped",
            "sms_reason": "no_bound_user",
        }

    @staticmethod
    @transaction.atomic
    def ban_device(
        *,
        device_id: str,
        reason_note: str = "",
        created_by_id: int | None = None,
    ) -> dict[str, Any]:
        normalized_device_id = AccessControlService.normalize_device_id(device_id)
        if not normalized_device_id:
            raise APIError("device_id_required", code=40061, status_code=400)
        device_entry, device_created = AccessControlService._ensure_entry(
            dimension=AccessDenyEntry.Dimension.DEVICE,
            dimension_value=normalized_device_id,
            source=AccessDenyEntry.Source.ADMIN,
            reason_note=reason_note,
            created_by_id=created_by_id,
        )
        return {
            "entry_id": device_entry.id,
            "device_id": normalized_device_id,
            "created": device_created,
            "sms_status": "skipped",
            "sms_reason": "device_only",
        }

    @staticmethod
    @transaction.atomic
    def revoke_entry(*, entry_id: int, revoked_by_id: int | None = None) -> AccessDenyEntry:
        entry = AccessDenyEntry.objects.select_for_update().filter(id=entry_id).first()
        if entry is None:
            raise APIError("deny_entry_not_found", code=40471, status_code=404)
        if entry.revoked_at is not None:
            return entry
        now = timezone.now()
        entry.revoked_at = now
        meta = dict(entry.metadata or {})
        meta["revoked_by_id"] = revoked_by_id
        entry.metadata = meta
        entry.save(update_fields=["revoked_at", "metadata", "updated_at"])

        if entry.dimension == AccessDenyEntry.Dimension.USER_ID:
            user_id = int(entry.dimension_value)
            User = get_user_model()
            still_banned = AccessControlService._active_queryset().filter(
                dimension=AccessDenyEntry.Dimension.USER_ID,
                dimension_value=str(user_id),
            ).exists()
            if not still_banned:
                user = User.objects.filter(id=user_id).first()
                if user is not None and not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
                    user.is_active = True
                    user.save(update_fields=["is_active"])
        return entry

    @staticmethod
    def parse_identifier_for_deny(identifier: str) -> dict[str, str]:
        identifier = (identifier or "").strip()
        result: dict[str, str] = {}
        if not identifier:
            return result
        if "@" in identifier:
            result["email"] = identifier
        elif identifier.startswith(("+", "00")) or (identifier.isdigit() and len(identifier) >= 7):
            result["phone"] = identifier
        return result
