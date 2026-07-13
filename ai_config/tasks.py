import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from notification_center.models import NotificationMessage
from notification_center.services import NotificationCenterService
from ai_config.models import TrialApplication, TrialApplicationRequest
from ai_config.services import TrialService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=5, ignore_result=True)
def approve_trial_application_request_task(self, request_id: int):
    """
    延迟自动审核任务：
    - 幂等：仅处理 pending 的申请流水
    - 更新 TrialApplication -> active（并写入 started/expires/approved）
    - 发送 APNs 通知，payload 触发客户端刷新 Pro 配置
    """
    try:
        with transaction.atomic():
            req = TrialApplicationRequest.objects.select_for_update().filter(id=int(request_id)).first()
            if req is None:
                logger.warning("trial.auto_approve.skipped request_not_found request_id=%s", request_id)
                return {"ok": False, "reason": "request_not_found"}

            if req.status != TrialApplication.Status.PENDING:
                return {"ok": True, "reason": "already_processed", "status": req.status}

            trial, _ = TrialApplication.objects.select_for_update().get_or_create(
                user_id=req.user_id,
                defaults={
                    "status": TrialApplication.Status.NONE,
                    "grant_source": TrialApplication.GrantSource.APPLICATION,
                },
            )
            trial = TrialService.ensure_status_fresh(trial=trial)
            if trial and trial.is_active_trial():
                # 已激活则仅标记流水为 active（不重复写试用周期）
                req.status = TrialApplication.Status.ACTIVE
                req.approved_at = timezone.now()
                req.rejected_at = None
                req.save(update_fields=["status", "approved_at", "rejected_at", "updated_at"])
                return {"ok": True, "reason": "trial_already_active"}

            now = timezone.now()
            trial.status = TrialApplication.Status.ACTIVE
            trial.grant_source = TrialApplication.GrantSource.APPLICATION
            trial.started_at = now
            trial.expires_at = TrialService._build_expiry(now)
            trial.approved_at = now
            trial.rejected_at = None
            trial.save(
                update_fields=[
                    "status",
                    "grant_source",
                    "started_at",
                    "expires_at",
                    "approved_at",
                    "rejected_at",
                    "updated_at",
                ]
            )

            req.status = TrialApplication.Status.ACTIVE
            req.approved_at = now
            req.rejected_at = None
            req.save(update_fields=["status", "approved_at", "rejected_at", "updated_at"])

        NotificationCenterService.send_to_user_sync(
            campaign_id=None,
            user_id=req.user_id,
            channels=[NotificationMessage.Channel.APNS],
            title="试用申请已通过",
            body="你的 Pro 模型试用申请已通过，现在可以使用服务端模型。",
            payload={
                "type": "ai_trial_application_result",
                "status": "active",
                "application_id": int(req.id),
                "refresh_ai_config": True,
                "route": "ai_settings",
            },
            created_by_id=None,
            request_id=f"trial_auto_approve:{req.id}",
            business_scene="membership.pro_trial.application_approved",
            business_reference_type="trial_application",
            business_id=str(req.id),
            idempotency_key=f"membership.pro_trial.application_approved:{req.id}:auto",
            source="ai_config.tasks",
        )
        return {"ok": True, "status": "active", "request_id": int(req.id)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("trial.auto_approve.failed request_id=%s reason=%s", request_id, str(exc))
        raise self.retry(exc=exc)
