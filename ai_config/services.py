from datetime import timedelta
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ai_config.models import TrialApplication, TrialApplicationRequest

logger = logging.getLogger(__name__)
flow_logger = logging.getLogger("accounts.flow")


class TrialService:
    @staticmethod
    def _trial_days() -> int:
        return int(getattr(settings, "AI_TRIAL_DURATION_DAYS", 15))

    @staticmethod
    def _build_expiry(started_at):
        return started_at + timedelta(days=TrialService._trial_days())

    @staticmethod
    @transaction.atomic
    def grant_auto_trial_if_eligible(*, user) -> TrialApplication:
        trial, _ = TrialApplication.objects.select_for_update().get_or_create(
            user=user,
            defaults={
                "status": TrialApplication.Status.NONE,
                "grant_source": TrialApplication.GrantSource.AUTO,
            },
        )
        if trial.is_active_trial():
            return trial
        if trial.status != TrialApplication.Status.NONE or trial.started_at is not None:
            # Auto trial is one-time only; expired/rejected users should not be silently re-granted.
            return trial

        now = timezone.now()
        trial.status = TrialApplication.Status.ACTIVE
        trial.grant_source = TrialApplication.GrantSource.AUTO
        trial.started_at = now
        trial.expires_at = TrialService._build_expiry(now)
        trial.applied_at = trial.applied_at or now
        trial.approved_at = now
        trial.rejected_at = None
        trial.note = "auto-granted on first successful sign-in"
        trial.save(
            update_fields=[
                "status",
                "grant_source",
                "started_at",
                "expires_at",
                "applied_at",
                "approved_at",
                "rejected_at",
                "note",
                "updated_at",
            ]
        )

        # 记录流水 + 发通知（若有可用 APNs 设备则触达；无设备不影响开通）
        latest_seq = (
            TrialApplicationRequest.objects.filter(user_id=user.id, source=TrialApplicationRequest.Source.AUTO)
            .order_by("-sequence")
            .values_list("sequence", flat=True)
            .first()
            or 0
        )
        TrialApplicationRequest.objects.create(
            user=user,
            source=TrialApplicationRequest.Source.AUTO,
            sequence=latest_seq + 1,
            status=TrialApplication.Status.ACTIVE,
            note="auto-granted on first successful sign-in",
            auto_approve_after_seconds=None,
            scheduled_at=None,
            approved_at=now,
            rejected_at=None,
        )
        return trial

    @staticmethod
    def try_grant_auto_trial_for_login_device(*, user, bundle_id: str, device_id: str, request_id: str) -> bool:
        """
        登录自动发放 Pro：仅当本次登录设备登记的 country_code == CN 时才允许触发。
        失败/跳过不影响登录流程，只记录日志。
        """
        bundle_id = (bundle_id or "").strip()
        device_id = (device_id or "").strip()
        if not bundle_id or not device_id or user is None:
            return False
        try:
            from accounts.models import TrustedDevice

            dev = TrustedDevice.objects.filter(
                bundle_id=bundle_id,
                device_id=device_id,
                is_revoked=False,
            ).first()
            cc = (dev.country_code if dev else "") or ""
            if cc != "CN":
                flow_logger.info(
                    "auth.trial.auto_grant.skipped_by_country",
                    extra={
                        "action": "auth.trial.auto_grant",
                        "request_id": request_id,
                        "user_id": getattr(user, "id", None),
                        "bundle_id": bundle_id,
                        "device_id": device_id,
                        "country_code": cc,
                    },
                )
                return False
            TrialService.grant_auto_trial_if_eligible(user=user)
            return True
        except Exception as exc:  # noqa: BLE001
            flow_logger.warning(
                "auth.trial.auto_grant.skipped",
                extra={
                    "action": "auth.trial.auto_grant",
                    "request_id": request_id,
                    "user_id": getattr(user, "id", None),
                    "bundle_id": bundle_id,
                    "device_id": device_id,
                    "reason": str(exc),
                },
            )
            return False

    @staticmethod
    @transaction.atomic
    def apply_trial(*, user, note: str = "", request_id: str = "") -> TrialApplicationRequest:
        trial, _ = TrialApplication.objects.select_for_update().get_or_create(
            user=user,
            defaults={
                "status": TrialApplication.Status.NONE,
                "grant_source": TrialApplication.GrantSource.APPLICATION,
            },
        )
        if trial.is_active_trial():
            # 已在试用期内则不重复创建申请流水
            latest_seq = (
                TrialApplicationRequest.objects.filter(user_id=user.id, source=TrialApplicationRequest.Source.APPLICATION)
                .order_by("-sequence")
                .values_list("sequence", flat=True)
                .first()
                or 0
            )
            return TrialApplicationRequest.objects.create(
                user=user,
                source=TrialApplicationRequest.Source.APPLICATION,
                sequence=latest_seq + 1,
                status=TrialApplication.Status.ACTIVE,
                note=(note or "").strip(),
                auto_approve_after_seconds=None,
                scheduled_at=None,
                approved_at=timezone.now(),
                rejected_at=None,
            )

        now = timezone.now()
        trial.applied_at = now
        trial.rejected_at = None
        trial.note = (note or "").strip()
        trial.status = TrialApplication.Status.PENDING
        trial.grant_source = TrialApplication.GrantSource.APPLICATION
        trial.started_at = None
        trial.expires_at = None
        trial.approved_at = None
        trial.save()

        latest_seq = (
            TrialApplicationRequest.objects.filter(user_id=user.id, source=TrialApplicationRequest.Source.APPLICATION)
            .order_by("-sequence")
            .values_list("sequence", flat=True)
            .first()
            or 0
        )
        seq = latest_seq + 1

        auto_delay = None
        if seq == 1:
            auto_delay = 4
        elif seq == 2:
            auto_delay = 15

        scheduled_at = now + timedelta(seconds=auto_delay) if auto_delay else None
        req = TrialApplicationRequest.objects.create(
            user=user,
            source=TrialApplicationRequest.Source.APPLICATION,
            sequence=seq,
            status=TrialApplication.Status.PENDING,
            note=trial.note,
            auto_approve_after_seconds=auto_delay,
            scheduled_at=scheduled_at,
        )

        if auto_delay:
            from ai_config.tasks import approve_trial_application_request_task

            try:
                # ignore_result 避免依赖 result backend（例如 Redis）导致接口侧 500。
                approve_trial_application_request_task.apply_async(args=[req.id], countdown=auto_delay, ignore_result=True)
            except Exception as exc:  # noqa: BLE001 - enqueue failure should not fail HTTP
                logger.error(
                    "trial.apply.enqueue_failed request_id=%s user_id=%s application_request_id=%s sequence=%s delay=%s reason=%s",
                    request_id or "",
                    getattr(user, "id", None),
                    req.id,
                    req.sequence,
                    auto_delay,
                    str(exc),
                )

        return req

    @staticmethod
    @transaction.atomic
    def ensure_status_fresh(*, trial: TrialApplication | None) -> TrialApplication | None:
        if trial is None:
            return None
        if trial.status == TrialApplication.Status.ACTIVE and trial.expires_at and trial.expires_at <= timezone.now():
            trial.status = TrialApplication.Status.EXPIRED
            trial.save(update_fields=["status", "updated_at"])
        return trial

    @staticmethod
    def is_pro_user(*, user) -> bool:
        trial = getattr(user, "trial_application", None)
        trial = TrialService.ensure_status_fresh(trial=trial)
        return bool(trial and trial.is_active_trial())
