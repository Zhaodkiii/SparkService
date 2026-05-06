import hashlib
import json
import logging
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone

from common.exceptions import APIError
from accounts.models import (
    AccountDeactivation,
    AccountDeactivationAudit,
    AccountProfile,
    EmailOTP,
    PhoneOTP,
    SocialIdentity,
    TrustedDevice,
)
from accounts.services.apple_identity_service import AppleIdentityService
from accounts.services.otp_service import OTPService
from accounts.services.phone_number_service import PhoneNumberService

logger = logging.getLogger(__name__)
flow_logger = logging.getLogger("accounts.flow")


class DeactivationService:
    ACTIVE_STATES = (
        AccountDeactivation.DeactivationState.REQUESTED,
        AccountDeactivation.DeactivationState.SCHEDULED,
        AccountDeactivation.DeactivationState.DATA_BACKED_UP,
        AccountDeactivation.DeactivationState.ANONYMIZED,
        AccountDeactivation.DeactivationState.RELATED_DATA_DELETED,
        AccountDeactivation.DeactivationState.ACCOUNT_DISABLED,
    )
    CANCELLABLE_STATES = (
        AccountDeactivation.DeactivationState.REQUESTED,
        AccountDeactivation.DeactivationState.SCHEDULED,
    )
    TERMINAL_STATES = (
        AccountDeactivation.DeactivationState.COMPLETED,
        AccountDeactivation.DeactivationState.CANCELLED,
    )

    @staticmethod
    @transaction.atomic
    def verify_deactivation_proof(*, user, verification: dict | None, request_id: str):
        if not verification:
            raise APIError("verification required", code=40061, status_code=400)

        verification_type = (verification.get("type") or "").strip().lower()
        now = timezone.now()

        if verification_type == "apple":
            identity_token = (verification.get("identity_token") or "").strip()
            user_identifier = (verification.get("user_identifier") or "").strip()
            allowed_bundle_ids = getattr(settings, "APPLE_ALLOWED_BUNDLE_IDS", [])
            if not allowed_bundle_ids:
                raise APIError("apple bundle audience not configured", code=40062, status_code=400)
            payload, matched_audience = AppleIdentityService.verify_identity_token(identity_token, audiences=allowed_bundle_ids)
            subject = (payload.get("sub") or "").strip()
            if not subject or subject != user_identifier:
                raise APIError("apple subject mismatch", code=40161, status_code=401)
            linked = SocialIdentity.objects.filter(
                user=user,
                provider=SocialIdentity.Provider.APPLE,
                provider_uid=subject,
                bundle_id=matched_audience,
            ).exists()
            if not linked:
                raise APIError("apple identity not linked to current user", code=40162, status_code=401)
            return {"type": "apple", "bundle_id": matched_audience}

        if verification_type == "email":
            email = (user.email or "").strip().lower()
            otp_id = (verification.get("otp_id") or "").strip()
            code = (verification.get("code") or "").strip()
            otp = EmailOTP.objects.select_for_update().filter(otp_id=otp_id, email=email).first()
            if not otp:
                raise APIError("OTP not found", code=40461, status_code=404)
            DeactivationService._verify_otp_row(otp=otp, code=code, now=now, invalid_code=40063)
            return {"type": "email", "otp_id": otp_id}

        if verification_type == "phone":
            profile = getattr(user, "profile", None)
            phone_number = getattr(profile, "phone_number", "") if profile else ""
            normalized_phone = PhoneNumberService.normalize_e164(phone_number)
            otp_id = (verification.get("otp_id") or "").strip()
            code = (verification.get("code") or "").strip()
            otp = PhoneOTP.objects.select_for_update().filter(otp_id=otp_id, phone_number=normalized_phone).first()
            if not otp:
                raise APIError("OTP not found", code=40462, status_code=404)
            DeactivationService._verify_otp_row(otp=otp, code=code, now=now, invalid_code=40064)
            return {"type": "phone", "otp_id": otp_id}

        raise APIError("unsupported verification type", code=40065, status_code=400)

    @staticmethod
    def _verify_otp_row(*, otp, code: str, now, invalid_code: int):
        if otp.used_at is not None:
            raise APIError("OTP already used", code=40066, status_code=400)
        if otp.expires_at <= now:
            raise APIError("OTP expired", code=40067, status_code=400)
        if otp.locked_until and otp.locked_until > now:
            raise APIError("OTP temporarily locked", code=42361, status_code=423)

        expected_hash = OTPService._hash_code(code)
        if expected_hash != otp.code_hash:
            otp.attempts += 1
            if otp.attempts >= OTPService.MAX_ATTEMPTS:
                otp.locked_until = now + timedelta(minutes=OTPService.LOCKOUT_MINUTES)
            otp.save(update_fields=["attempts", "locked_until"])
            raise APIError("Invalid OTP", code=invalid_code, status_code=400)

        otp.used_at = now
        otp.save(update_fields=["used_at"])

    @staticmethod
    @transaction.atomic
    def request_deactivation(
        *,
        user,
        request_id: str,
        reason: str = "",
        immediate_deactivation: bool = True,
        countdown_hours: int = 0,
        data_retention_days: int = 30,
        anonymize_personal_data: bool = True,
        delete_related_data: bool = True,
    ):
        flow_logger.info(
            "account.deactivation.service.request.begin",
            extra={"action": "account.deactivation.service.request", "request_id": request_id, "user_id": user.id},
        )
        existing = (
            AccountDeactivation.objects.select_for_update()
            .filter(user=user, state__in=DeactivationService.ACTIVE_STATES)
            .order_by("-id")
            .first()
        )
        if existing:
            return {"deactivation_id": existing.id, "state": existing.state, "scheduled_at": existing.scheduled_at, "reused": True}

        now = timezone.now()
        scheduled_at = now if immediate_deactivation else now + timedelta(hours=max(1, int(countdown_hours or 24)))
        obj = AccountDeactivation.objects.create(
            user=user,
            state=AccountDeactivation.DeactivationState.SCHEDULED,
            requested_at=now,
            scheduled_at=scheduled_at,
            request_id=request_id or "",
            reason=(reason or "")[:256],
            data_retention_days=max(0, int(data_retention_days or 0)),
            anonymize_personal_data=bool(anonymize_personal_data),
            delete_related_data=bool(delete_related_data),
        )
        AccountDeactivationAudit.objects.create(
            deactivation=obj,
            action=AccountDeactivationAudit.AuditAction.REQUESTED,
            request_id=request_id or "",
            details={
                "scheduled_at": scheduled_at.isoformat(),
                "immediate_deactivation": bool(immediate_deactivation),
                "countdown_hours": 0 if immediate_deactivation else max(1, int(countdown_hours or 24)),
                "data_retention_days": obj.data_retention_days,
                "anonymize_personal_data": obj.anonymize_personal_data,
                "delete_related_data": obj.delete_related_data,
            },
        )
        return {
            "deactivation_id": obj.id,
            "state": obj.state,
            "scheduled_at": obj.scheduled_at,
            "immediate_deactivation": immediate_deactivation,
            "countdown_hours": 0 if immediate_deactivation else max(1, int(countdown_hours or 24)),
            "reused": False,
        }

    @staticmethod
    @transaction.atomic
    def process_deactivation(*, deactivation_id: int, request_id: str, task_id: str | None = None):
        flow_logger.info(
            "account.deactivation.service.process.begin",
            extra={"action": "account.deactivation.service.process", "request_id": request_id, "deactivation_id": deactivation_id, "task_id": task_id or ""},
        )
        now = timezone.now()
        obj = AccountDeactivation.objects.select_for_update().filter(id=deactivation_id).first()
        if not obj:
            raise APIError("deactivation not found", code=40402, status_code=404)
        if obj.state in DeactivationService.TERMINAL_STATES:
            return {"deactivation_id": obj.id, "state": obj.state, "noop": True}
        if obj.scheduled_at and obj.scheduled_at > now and obj.state in (
            AccountDeactivation.DeactivationState.REQUESTED,
            AccountDeactivation.DeactivationState.SCHEDULED,
        ):
            return {"deactivation_id": obj.id, "state": obj.state, "noop": True, "scheduled_at": obj.scheduled_at}

        user = get_user_model().objects.select_for_update().get(id=obj.user_id)
        profile = getattr(user, "profile", None)
        if not obj.freeze_email:
            obj.freeze_email = user.email or ""
        if not obj.freeze_phone_number:
            obj.freeze_phone_number = getattr(profile, "phone_number", "") if profile else ""
        if obj.processed_at is None:
            obj.processed_at = now
        obj.save(update_fields=["freeze_email", "freeze_phone_number", "processed_at"])

        if obj.state in (AccountDeactivation.DeactivationState.REQUESTED, AccountDeactivation.DeactivationState.SCHEDULED):
            DeactivationService.backup_user_data(deactivation=obj, user=user, request_id=request_id)

        if obj.state == AccountDeactivation.DeactivationState.DATA_BACKED_UP:
            DeactivationService.anonymize_user_data(deactivation=obj, user=user, request_id=request_id)

        if obj.state == AccountDeactivation.DeactivationState.ANONYMIZED:
            DeactivationService.delete_related_data(deactivation=obj, user=user, request_id=request_id)

        if obj.state == AccountDeactivation.DeactivationState.RELATED_DATA_DELETED:
            DeactivationService.disable_account(deactivation=obj, user=user, request_id=request_id)

        if obj.state == AccountDeactivation.DeactivationState.ACCOUNT_DISABLED:
            DeactivationService.complete_deactivation(deactivation=obj, request_id=request_id)

        flow_logger.info(
            "account.deactivation.service.process.success",
            extra={"action": "account.deactivation.service.process", "request_id": request_id, "deactivation_id": obj.id, "state": obj.state},
        )
        return DeactivationService.build_status_payload(obj, request_id=request_id) | {"noop": False}

    @staticmethod
    def backup_user_data(*, deactivation: AccountDeactivation, user, request_id: str):
        summary, payload = DeactivationService._build_backup_payload(deactivation=deactivation, user=user)
        backup_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        checksum = hashlib.sha256(backup_bytes).hexdigest()
        backup_name = f"account_deactivation_backups/user_{user.id}/deactivation_{deactivation.id}.json"
        saved_name = default_storage.save(backup_name, ContentFile(backup_bytes))

        expires_at = None
        if deactivation.data_retention_days > 0:
            expires_at = timezone.now() + timedelta(days=deactivation.data_retention_days)

        deactivation.backup_uri = saved_name
        deactivation.backup_checksum = checksum
        deactivation.backup_expires_at = expires_at
        deactivation.state = AccountDeactivation.DeactivationState.DATA_BACKED_UP
        deactivation.save(update_fields=["backup_uri", "backup_checksum", "backup_expires_at", "state"])
        AccountDeactivationAudit.objects.create(
            deactivation=deactivation,
            action=AccountDeactivationAudit.AuditAction.DATA_BACKUP,
            request_id=request_id or "",
            details={
                "backup_uri": saved_name,
                "backup_checksum": checksum,
                "backup_expires_at": expires_at.isoformat() if expires_at else None,
                "summary": summary,
            },
        )

    @staticmethod
    def anonymize_user_data(*, deactivation: AccountDeactivation, user, request_id: str):
        if deactivation.anonymize_personal_data:
            anon_suffix = f"{deactivation.id}_{int(timezone.now().timestamp())}"
            user.username = f"deleted_user_{anon_suffix}"
            user.email = f"deleted_{anon_suffix}@anonymized.local"
            user.first_name = ""
            user.last_name = ""
            user.save(update_fields=["username", "email", "first_name", "last_name"])

            profile = getattr(user, "profile", None)
            if profile:
                profile.phone_number = ""
                profile.save(update_fields=["phone_number"])

            TrustedDevice.objects.filter(user=user).update(push_token="", device_name="", is_revoked=True)
            DeactivationService._anonymize_notification_receivers(user_id=user.id)

        deactivation.state = AccountDeactivation.DeactivationState.ANONYMIZED
        deactivation.save(update_fields=["state"])
        AccountDeactivationAudit.objects.create(
            deactivation=deactivation,
            action=AccountDeactivationAudit.AuditAction.DATA_ANONYMIZE,
            request_id=request_id or "",
            details={
                "anonymized": bool(deactivation.anonymize_personal_data),
                "email_hash": DeactivationService._hash_identifier(deactivation.freeze_email),
                "phone_hash": DeactivationService._hash_identifier(deactivation.freeze_phone_number),
            },
        )

    @staticmethod
    def delete_related_data(*, deactivation: AccountDeactivation, user, request_id: str):
        stats: dict[str, int] = {}
        if deactivation.delete_related_data:
            stats.update(DeactivationService._delete_account_related_data(deactivation=deactivation, user=user))
            stats.update(DeactivationService._delete_domain_related_data(user=user))

        deactivation.state = AccountDeactivation.DeactivationState.RELATED_DATA_DELETED
        deactivation.save(update_fields=["state"])
        AccountDeactivationAudit.objects.create(
            deactivation=deactivation,
            action=AccountDeactivationAudit.AuditAction.RELATED_DATA_DELETE,
            request_id=request_id or "",
            details={"deleted": bool(deactivation.delete_related_data), "stats": stats},
        )

    @staticmethod
    def disable_account(*, deactivation: AccountDeactivation, user, request_id: str):
        user.is_active = False
        user.save(update_fields=["is_active"])
        TrustedDevice.objects.filter(user=user).update(is_revoked=True, push_token="")
        DeactivationService._blacklist_refresh_tokens(user=user)

        deactivation.state = AccountDeactivation.DeactivationState.ACCOUNT_DISABLED
        deactivation.save(update_fields=["state"])
        AccountDeactivationAudit.objects.create(
            deactivation=deactivation,
            action=AccountDeactivationAudit.AuditAction.ACCOUNT_DEACTIVATE,
            request_id=request_id or "",
            details={"user_active": False, "trusted_devices_revoked": True},
        )

    @staticmethod
    def complete_deactivation(*, deactivation: AccountDeactivation, request_id: str):
        deactivation.state = AccountDeactivation.DeactivationState.COMPLETED
        deactivation.completed_at = timezone.now()
        deactivation.save(update_fields=["state", "completed_at"])
        AccountDeactivationAudit.objects.create(
            deactivation=deactivation,
            action=AccountDeactivationAudit.AuditAction.COMPLETED,
            request_id=request_id or "",
            details={
                "backup_uri": deactivation.backup_uri,
                "backup_checksum": deactivation.backup_checksum,
                "backup_expires_at": deactivation.backup_expires_at.isoformat() if deactivation.backup_expires_at else None,
            },
        )

    @staticmethod
    def build_status_payload(obj: AccountDeactivation, *, request_id: str = ""):
        stage_order = [
            AccountDeactivation.DeactivationState.SCHEDULED,
            AccountDeactivation.DeactivationState.DATA_BACKED_UP,
            AccountDeactivation.DeactivationState.ANONYMIZED,
            AccountDeactivation.DeactivationState.RELATED_DATA_DELETED,
            AccountDeactivation.DeactivationState.ACCOUNT_DISABLED,
            AccountDeactivation.DeactivationState.COMPLETED,
        ]
        if obj.state == AccountDeactivation.DeactivationState.COMPLETED:
            percentage = 100
        elif obj.state in stage_order:
            percentage = int((stage_order.index(obj.state) / (len(stage_order) - 1)) * 100)
        elif obj.state == AccountDeactivation.DeactivationState.CANCELLED:
            percentage = 0
        elif obj.state == AccountDeactivation.DeactivationState.FAILED:
            percentage = 0
        else:
            percentage = 0

        remaining_seconds = 0
        if obj.state == AccountDeactivation.DeactivationState.SCHEDULED and obj.scheduled_at:
            remaining_seconds = max(0, int((obj.scheduled_at - timezone.now()).total_seconds()))
        can_cancel = obj.state in DeactivationService.CANCELLABLE_STATES
        if can_cancel and obj.scheduled_at:
            can_cancel = obj.scheduled_at > timezone.now()

        return {
            "deactivation_id": obj.id,
            "state": obj.state,
            "scheduled_at": obj.scheduled_at,
            "processed_at": obj.processed_at,
            "completed_at": obj.completed_at,
            "cancelled_at": obj.cancelled_at,
            "failed_at": obj.failed_at,
            "can_cancel": can_cancel,
            "countdown": {
                "total_seconds": remaining_seconds,
                "expired": remaining_seconds == 0,
            },
            "progress": {
                "stage": obj.state,
                "percentage": percentage,
                "completed_stages": list(obj.audits.order_by("created_at").values_list("action", flat=True)),
            },
            "backup": {
                "uri": obj.backup_uri,
                "checksum": obj.backup_checksum,
                "expires_at": obj.backup_expires_at,
            },
            "error_message": obj.error_message,
        }

    @staticmethod
    @transaction.atomic
    def mark_failed(*, deactivation_id: int, request_id: str, error_message: str):
        obj = AccountDeactivation.objects.select_for_update().filter(id=deactivation_id).first()
        if not obj or obj.state in DeactivationService.TERMINAL_STATES:
            return

        obj.state = AccountDeactivation.DeactivationState.FAILED
        obj.failed_at = timezone.now()
        obj.error_message = (error_message or "")[:2000]
        obj.save(update_fields=["state", "failed_at", "error_message"])

        AccountDeactivationAudit.objects.create(
            deactivation=obj,
            action=AccountDeactivationAudit.AuditAction.FAILED,
            request_id=request_id or "",
            details={"error": (error_message or "")[:500]},
        )

    @staticmethod
    @transaction.atomic
    def cancel_deactivation(*, deactivation_id: int, user_id: int, request_id: str, reason: str = ""):
        obj = AccountDeactivation.objects.select_for_update().filter(id=deactivation_id, user_id=user_id).first()
        if not obj:
            raise APIError("deactivation not found", code=40402, status_code=404)
        if obj.state in DeactivationService.TERMINAL_STATES:
            return {"deactivation_id": obj.id, "state": obj.state, "noop": True}
        if obj.state not in DeactivationService.CANCELLABLE_STATES:
            raise APIError("deactivation is already irreversible", code=40961, status_code=409)
        if obj.scheduled_at and obj.scheduled_at <= timezone.now():
            raise APIError("deactivation countdown expired", code=40962, status_code=409)

        obj.state = AccountDeactivation.DeactivationState.CANCELLED
        obj.cancelled_at = timezone.now()
        obj.save(update_fields=["state", "cancelled_at"])
        AccountDeactivationAudit.objects.create(
            deactivation=obj,
            action=AccountDeactivationAudit.AuditAction.CANCELLED,
            request_id=request_id or "",
            details={"reason": reason or "", "by_user_id": user_id},
        )
        return {"deactivation_id": obj.id, "state": obj.state, "noop": False}

    @staticmethod
    def cancel_pending_on_login(*, user, request_id: str = "", reason: str = "login_auto_cancel"):
        obj = (
            AccountDeactivation.objects.filter(user=user, state__in=DeactivationService.CANCELLABLE_STATES)
            .order_by("-id")
            .first()
        )
        if not obj:
            return {"cancelled": False, "deactivation_id": None}
        result = DeactivationService.cancel_deactivation(
            deactivation_id=obj.id,
            user_id=user.id,
            request_id=request_id,
            reason=reason,
        )
        return {"cancelled": not result.get("noop", False), "deactivation_id": obj.id}

    @staticmethod
    def _build_backup_payload(*, deactivation: AccountDeactivation, user):
        profile = getattr(user, "profile", None)
        payload = {
            "schema_version": 1,
            "deactivation_id": deactivation.id,
            "user_id": user.id,
            "generated_at": timezone.now().isoformat(),
            "retention_days": deactivation.data_retention_days,
            "user": model_to_dict(user, fields=["id", "username", "email", "first_name", "last_name", "is_active", "date_joined", "last_login"]),
            "profile": model_to_dict(profile) if profile else None,
            "accounts": {},
            "domain_indexes": {},
        }
        payload["accounts"]["social_identities"] = DeactivationService._rows_for_queryset(SocialIdentity.objects.filter(user=user))
        payload["accounts"]["trusted_devices"] = DeactivationService._rows_for_queryset(TrustedDevice.objects.filter(user=user))
        payload["accounts"]["email_otps"] = DeactivationService._rows_for_queryset(EmailOTP.objects.filter(email=user.email))
        if profile and profile.phone_number:
            payload["accounts"]["phone_otps"] = DeactivationService._rows_for_queryset(PhoneOTP.objects.filter(phone_number=profile.phone_number))
        else:
            payload["accounts"]["phone_otps"] = []

        summary = {
            "accounts.social_identities": len(payload["accounts"]["social_identities"]),
            "accounts.trusted_devices": len(payload["accounts"]["trusted_devices"]),
            "accounts.email_otps": len(payload["accounts"]["email_otps"]),
            "accounts.phone_otps": len(payload["accounts"]["phone_otps"]),
        }
        for model in apps.get_models():
            if model._meta.app_label in {"medical", "chat_sync", "file_manager", "task_system", "ai_config"}:
                data = DeactivationService._model_user_index(model=model, user_id=user.id)
                if data["count"] > 0:
                    key = f"{model._meta.app_label}.{model.__name__}"
                    payload["domain_indexes"][key] = data
                    summary[key] = data["count"]
        return summary, payload

    @staticmethod
    def _rows_for_queryset(queryset, limit: int = 10000):
        rows = []
        for obj in queryset[:limit]:
            data = model_to_dict(obj)
            rows.append(DeactivationService._json_safe(data))
        return rows

    @staticmethod
    def _model_user_index(*, model, user_id: int):
        querysets = []
        for field_name in ("user", "creator", "created_by", "operator"):
            try:
                field = model._meta.get_field(field_name)
            except Exception:
                continue
            if not getattr(field, "remote_field", None):
                continue
            querysets.append(model._default_manager.filter(**{field.attname: user_id}))
        count = 0
        pks = []
        for qs in querysets:
            ids = list(qs.values_list("pk", flat=True)[:10000])
            count += len(ids)
            pks.extend([str(pk) for pk in ids])
        return {"count": count, "pks": sorted(set(pks))}

    @staticmethod
    def _delete_account_related_data(*, deactivation: AccountDeactivation, user):
        stats = {}
        stats["social_identities"] = SocialIdentity.objects.filter(user=user).delete()[0]
        stats["email_otps"] = EmailOTP.objects.filter(email=deactivation.freeze_email).delete()[0] if deactivation.freeze_email else 0
        stats["phone_otps"] = PhoneOTP.objects.filter(phone_number=deactivation.freeze_phone_number).delete()[0] if deactivation.freeze_phone_number else 0
        stats["trusted_devices_revoked"] = TrustedDevice.objects.filter(user=user).update(is_revoked=True, push_token="", device_name="")
        stats["profile_deleted"] = AccountProfile.objects.filter(user=user).delete()[0]
        return stats

    @staticmethod
    def _delete_domain_related_data(*, user):
        stats: dict[str, int] = {}
        now = timezone.now()
        DeactivationService._soft_delete_queryset("chat_sync", "ChatMessage", {"user_id": user.id}, {"tombstone": True}, stats)
        DeactivationService._soft_delete_queryset("chat_sync", "ChatThread", {"user_id": user.id}, {"is_deleted": True, "deleted_at": now}, stats)
        DeactivationService._soft_delete_queryset("file_manager", "ManagedFile", {"user_id": user.id}, {"is_deleted": True, "deleted_at": now}, stats)
        DeactivationService._soft_delete_medical(user=user, now=now, stats=stats)
        DeactivationService._cleanup_tasks(user=user, stats=stats)
        DeactivationService._delete_optional_model("ai_config", "TrialApplication", {"user_id": user.id}, stats)
        return stats

    @staticmethod
    def _soft_delete_queryset(app_label: str, model_name: str, filters: dict, updates: dict, stats: dict):
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            return
        count = model.objects.filter(**filters).update(**updates)
        stats[f"{app_label}.{model_name}"] = count

    @staticmethod
    def _soft_delete_medical(*, user, now, stats: dict):
        for model in apps.get_models():
            if model._meta.app_label != "medical":
                continue
            field_names = {field.name for field in model._meta.fields}
            if "user" not in field_names or "is_deleted" not in field_names:
                continue
            manager = getattr(model, "all_objects", model.objects)
            count = manager.filter(user_id=user.id, is_deleted=False).update(is_deleted=True, deleted_at=now)
            stats[f"medical.{model.__name__}"] = count

    @staticmethod
    def _cleanup_tasks(*, user, stats: dict):
        for model_name, field_name in (
            ("Task", "creator"),
            ("TaskExecution", "user"),
            ("TaskMedical", "created_by"),
            ("TaskExercise", "created_by"),
            ("TaskDiet", "created_by"),
            ("TaskPlan", "creator"),
        ):
            DeactivationService._delete_optional_model("task_system", model_name, {f"{field_name}_id": user.id}, stats)

    @staticmethod
    def _delete_optional_model(app_label: str, model_name: str, filters: dict, stats: dict):
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            return
        stats[f"{app_label}.{model_name}"] = model.objects.filter(**filters).delete()[0]

    @staticmethod
    def _anonymize_notification_receivers(*, user_id: int):
        try:
            notification_message = apps.get_model("accounts", "NotificationMessage")
        except LookupError:
            return
        notification_message.objects.filter(user_id=user_id).update(receiver_email="", receiver_phone="")

    @staticmethod
    def _blacklist_refresh_tokens(*, user):
        try:
            outstanding_token = apps.get_model("token_blacklist", "OutstandingToken")
            blacklisted_token = apps.get_model("token_blacklist", "BlacklistedToken")
        except LookupError:
            return
        for token in outstanding_token.objects.filter(user=user):
            blacklisted_token.objects.get_or_create(token=token)

    @staticmethod
    def _hash_identifier(value: str):
        if not value:
            return ""
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _json_safe(value):
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
