import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from common.exceptions import APIError
from accounts.models import (
    AccountDeactivation,
    AccountDeactivationAudit,
    EmailOTP,
    PhoneOTP,
)

logger = logging.getLogger(__name__)
flow_logger = logging.getLogger("accounts.flow")


class DeactivationService:
    @staticmethod
    def request_deactivation(*, user, request_id: str):
        flow_logger.info(
            "account.deactivation.service.request.begin",
            extra={"action": "account.deactivation.service.request", "request_id": request_id, "user_id": user.id},
        )
        # Idempotency: reuse active deactivation workflow if one already exists.
        existing = (
            AccountDeactivation.objects.filter(
                user=user,
                state__in=[
                    AccountDeactivation.DeactivationState.REQUESTED,
                    AccountDeactivation.DeactivationState.SCHEDULED,
                    AccountDeactivation.DeactivationState.FROZEN,
                    AccountDeactivation.DeactivationState.ANONYMIZED,
                    AccountDeactivation.DeactivationState.CLEANED_UP,
                ],
            )
            .order_by("-id")
            .first()
        )
        if existing:
            flow_logger.info(
                "account.deactivation.service.request.reused",
                extra={
                    "action": "account.deactivation.service.request",
                    "request_id": request_id,
                    "user_id": user.id,
                    "deactivation_id": existing.id,
                    "state": existing.state,
                },
            )
            return {"deactivation_id": existing.id, "state": existing.state, "reused": True}

        now = timezone.now()
        obj = AccountDeactivation.objects.create(
            user=user,
            state=AccountDeactivation.DeactivationState.SCHEDULED,
            requested_at=now,
            scheduled_at=now,
            request_id=request_id or "",
        )
        flow_logger.info(
            "account.deactivation.service.request.created",
            extra={
                "action": "account.deactivation.service.request",
                "request_id": request_id,
                "user_id": user.id,
                "deactivation_id": obj.id,
                "state": obj.state,
            },
        )
        return {"deactivation_id": obj.id, "state": obj.state, "reused": False}

    @staticmethod
    @transaction.atomic
    def process_deactivation(*, deactivation_id: int, request_id: str, task_id: str | None = None):
        flow_logger.info(
            "account.deactivation.service.process.begin",
            extra={
                "action": "account.deactivation.service.process",
                "request_id": request_id,
                "deactivation_id": deactivation_id,
                "task_id": task_id or "",
            },
        )
        now = timezone.now()
        obj = (
            AccountDeactivation.objects.select_for_update()
            .filter(id=deactivation_id)
            .first()
        )
        if not obj:
            flow_logger.warning(
                "account.deactivation.service.process.failed",
                extra={
                    "action": "account.deactivation.service.process",
                    "request_id": request_id,
                    "deactivation_id": deactivation_id,
                    "reason": "deactivation_not_found",
                },
            )
            raise APIError("deactivation not found", code=40402, status_code=404)

        if obj.state in (
            AccountDeactivation.DeactivationState.DEACTIVATED,
            AccountDeactivation.DeactivationState.CANCELLED,
        ):
            flow_logger.info(
                "account.deactivation.service.process.noop",
                extra={
                    "action": "account.deactivation.service.process",
                    "request_id": request_id,
                    "deactivation_id": obj.id,
                    "state": obj.state,
                },
            )
            return {"deactivation_id": obj.id, "state": obj.state, "noop": True}

        user = get_user_model().objects.select_for_update().get(id=obj.user_id)
        profile = getattr(user, "profile", None)
        freeze_phone = getattr(profile, "phone_number", "") if profile else ""

        # Step 1: Freeze identifiers (compliance-safe order)
        if obj.state == AccountDeactivation.DeactivationState.SCHEDULED or not obj.freeze_email:
            flow_logger.info(
                "account.deactivation.service.process.step",
                extra={"action": "account.deactivation.service.process", "request_id": request_id, "deactivation_id": obj.id, "step": "freeze_identifiers"},
            )
            AccountDeactivationAudit.objects.create(
                deactivation=obj,
                action=AccountDeactivationAudit.AuditAction.FREEZE_IDENTIFIERS,
                request_id=request_id or "",
                details={"email": user.email, "phone": freeze_phone},
            )
            obj.freeze_email = user.email or ""
            obj.freeze_phone_number = freeze_phone or ""
            obj.processed_at = obj.processed_at or now
            obj.state = AccountDeactivation.DeactivationState.FROZEN
            obj.save(update_fields=["freeze_email", "freeze_phone_number", "processed_at", "state"])

        # Step 2: Anonymize
        if obj.state == AccountDeactivation.DeactivationState.FROZEN:
            flow_logger.info(
                "account.deactivation.service.process.step",
                extra={"action": "account.deactivation.service.process", "request_id": request_id, "deactivation_id": obj.id, "step": "anonymize"},
            )
            AccountDeactivationAudit.objects.create(
                deactivation=obj,
                action=AccountDeactivationAudit.AuditAction.ANONYMIZE,
                request_id=request_id or "",
            )
            obj.state = AccountDeactivation.DeactivationState.ANONYMIZED
            # Ensure unique email value.
            user.email = f"anon+{obj.id}+{int(now.timestamp())}@example.com"
            if profile:
                profile.phone_number = ""
                profile.save(update_fields=["phone_number"])
            user.save(update_fields=["email"])
            obj.save(update_fields=["state"])

        # Step 3: Cleanup (delete by frozen identifiers)
        if obj.state == AccountDeactivation.DeactivationState.ANONYMIZED:
            flow_logger.info(
                "account.deactivation.service.process.step",
                extra={"action": "account.deactivation.service.process", "request_id": request_id, "deactivation_id": obj.id, "step": "cleanup_otps"},
            )
            AccountDeactivationAudit.objects.create(
                deactivation=obj,
                action=AccountDeactivationAudit.AuditAction.CLEANUP_OTPS,
                request_id=request_id or "",
                details={"freeze_email": obj.freeze_email, "freeze_phone_number": obj.freeze_phone_number},
            )
            if obj.freeze_email:
                EmailOTP.objects.filter(email=obj.freeze_email).delete()
            if obj.freeze_phone_number:
                PhoneOTP.objects.filter(phone_number=obj.freeze_phone_number).delete()
            obj.state = AccountDeactivation.DeactivationState.CLEANED_UP
            obj.save(update_fields=["state"])

        # Step 4: Deactivate user
        if obj.state == AccountDeactivation.DeactivationState.CLEANED_UP:
            flow_logger.info(
                "account.deactivation.service.process.step",
                extra={"action": "account.deactivation.service.process", "request_id": request_id, "deactivation_id": obj.id, "step": "deactivate_user"},
            )
            AccountDeactivationAudit.objects.create(
                deactivation=obj,
                action=AccountDeactivationAudit.AuditAction.DEACTIVATE_USER,
                request_id=request_id or "",
            )
            user.is_active = False
            user.save(update_fields=["is_active"])
            obj.state = AccountDeactivation.DeactivationState.DEACTIVATED
            obj.completed_at = now
            obj.save(update_fields=["state", "completed_at"])

        flow_logger.info(
            "account.deactivation.service.process.success",
            extra={
                "action": "account.deactivation.service.process",
                "request_id": request_id,
                "deactivation_id": obj.id,
                "state": obj.state,
            },
        )
        return {"deactivation_id": obj.id, "state": obj.state, "noop": False}

    @staticmethod
    @transaction.atomic
    def mark_failed(*, deactivation_id: int, request_id: str, error_message: str):
        flow_logger.warning(
            "account.deactivation.service.mark_failed.begin",
            extra={
                "action": "account.deactivation.service.mark_failed",
                "request_id": request_id,
                "deactivation_id": deactivation_id,
            },
        )
        obj = (
            AccountDeactivation.objects.select_for_update()
            .filter(id=deactivation_id)
            .first()
        )
        if not obj:
            flow_logger.warning(
                "account.deactivation.service.mark_failed.skip",
                extra={
                    "action": "account.deactivation.service.mark_failed",
                    "request_id": request_id,
                    "deactivation_id": deactivation_id,
                    "reason": "not_found",
                },
            )
            return
        if obj.state in (
            AccountDeactivation.DeactivationState.DEACTIVATED,
            AccountDeactivation.DeactivationState.CANCELLED,
        ):
            flow_logger.info(
                "account.deactivation.service.mark_failed.skip",
                extra={
                    "action": "account.deactivation.service.mark_failed",
                    "request_id": request_id,
                    "deactivation_id": deactivation_id,
                    "reason": "already_terminal",
                    "state": obj.state,
                },
            )
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
        flow_logger.error(
            "account.deactivation.service.mark_failed.done",
            extra={
                "action": "account.deactivation.service.mark_failed",
                "request_id": request_id,
                "deactivation_id": deactivation_id,
                "state": obj.state,
                "error_message": (error_message or "")[:500],
            },
        )
