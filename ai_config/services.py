from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ai_config.models import TrialApplication


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
        return trial

    @staticmethod
    @transaction.atomic
    def apply_trial(*, user, note: str = "") -> TrialApplication:
        trial, _ = TrialApplication.objects.select_for_update().get_or_create(
            user=user,
            defaults={
                "status": TrialApplication.Status.NONE,
                "grant_source": TrialApplication.GrantSource.APPLICATION,
            },
        )
        if trial.is_active_trial():
            return trial

        now = timezone.now()
        auto_approve = bool(getattr(settings, "AI_TRIAL_AUTO_APPROVE_APPLICATIONS", True))
        trial.applied_at = now
        trial.rejected_at = None
        trial.note = (note or "").strip()

        if auto_approve:
            trial.status = TrialApplication.Status.ACTIVE
            trial.grant_source = TrialApplication.GrantSource.APPLICATION
            trial.started_at = now
            trial.expires_at = TrialService._build_expiry(now)
            trial.approved_at = now
        else:
            trial.status = TrialApplication.Status.PENDING
            trial.grant_source = TrialApplication.GrantSource.APPLICATION
            trial.started_at = None
            trial.expires_at = None
            trial.approved_at = None

        trial.save()
        return trial

    @staticmethod
    @transaction.atomic
    def ensure_status_fresh(*, trial: TrialApplication | None) -> TrialApplication | None:
        if trial is None:
            return None
        if trial.status == TrialApplication.Status.ACTIVE and trial.expires_at and trial.expires_at <= timezone.now():
            trial.status = TrialApplication.Status.EXPIRED
            trial.save(update_fields=["status", "updated_at"])
        return trial
