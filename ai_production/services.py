from datetime import timedelta
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from common.exceptions import APIError
from .models import ProductionControl, ProductionLedger, ProductionPolicy, ProductionTask, ProductionWindow


def lock_account(user):
    get_user_model().objects.select_for_update().get(pk=user.pk)


def policy_at(now):
    policy = ProductionPolicy.objects.filter(effective_at__lte=now).order_by("-effective_at", "-pk").first()
    if not policy or not policy.enabled or ProductionControl.objects.filter(pk=1, accepting=False).exists():
        raise APIError("AI 制作暂未开放，请稍后重试", code=50301, status_code=503)
    return policy


def record(task, event, actor=None, reason=""):
    ProductionLedger.objects.create(
        task=task, reservation_id=task.reservation_id, event=event,
        short_window=task.short_window, weekly_window=task.weekly_window,
        actor=actor, reason=reason,
    )


def release(task, state, actor=None, reason=""):
    for window in (task.short_window, task.weekly_window):
        window.reserved -= 1
        window.save(update_fields=["reserved"])
    task.state = state
    task.version += 1
    task.save()
    record(task, "release", actor, reason)


def expire(user, now):
    tasks = ProductionTask.objects.filter(
        account=user, state__in=["reserved", "paused"], expires_at__lte=now,
    ).select_related("short_window", "weekly_window")
    # Refresh each window because multiple tasks may reference the same window.
    for task in tasks:
        task.short_window.refresh_from_db()
        task.weekly_window.refresh_from_db()
        release(task, "expired", reason="预占到期")


def windows(user, now, policy):
    result = []
    for kind, hours, limit in (("short", 5, policy.short_limit), ("weekly", 168, policy.weekly_limit)):
        window = ProductionWindow.objects.filter(
            account=user, kind=kind, starts_at__lte=now, ends_at__gt=now,
        ).order_by("-starts_at").first()
        if window is None:
            window = ProductionWindow(
                account=user, kind=kind, starts_at=now, ends_at=now + timedelta(hours=hours),
                limit=limit, policy=policy,
            )
        result.append(window)
    return result


def reserve(user, now, policy):
    selected = windows(user, now, policy)
    blocked = [w for w in selected if w.limit <= w.used + w.reserved]
    if blocked:
        raise APIError(
            "制作额度已用完，请查看恢复时间", code=42901, status_code=429,
            details={"windows": [w.kind for w in blocked],
                     "reset_at": max(w.ends_at for w in blocked).isoformat()},
        )
    for window in selected:
        window.reserved += 1
        window.save()
    return selected


@transaction.atomic
def quota(user):
    lock_account(user)
    now = timezone.now()
    expire(user, now)
    policy = ProductionPolicy.objects.filter(effective_at__lte=now).order_by("-effective_at", "-pk").first()
    maintenance = not policy or not policy.enabled or ProductionControl.objects.filter(pk=1, accepting=False).exists()
    if not policy:
        return {"server_time": now.isoformat(), "policy_version": 0, "service_status": "unconfigured",
                "can_start": False, "blocked_reasons": ["unconfigured"], "next_eligible_at": None, "windows": []}
    selected = windows(user, now, policy)
    blocked = [w for w in selected if w.limit <= w.used + w.reserved]
    recoverable = blocked and all(w.pk and w.limit > 0 for w in blocked)
    return {
        "server_time": now.isoformat(), "policy_version": policy.pk,
        "service_status": "maintenance" if maintenance else "available",
        "can_start": not blocked and not maintenance,
        "blocked_reasons": (["maintenance"] if maintenance else []) + [w.kind + "_limit" for w in blocked],
        "next_eligible_at": max(w.ends_at for w in blocked).isoformat() if recoverable and not maintenance else None,
        "windows": [
            {"window_id": w.pk, "kind": w.kind, "limit": w.limit,
             "used": w.used, "reserved": w.reserved,
             "available": max(0, w.limit - w.used - w.reserved),
             "status": "active" if w.pk else (
                 "awaiting_first_use" if ProductionWindow.objects.filter(account=user, kind=w.kind).exists()
                 else "not_started"),
             "starts_at": w.starts_at.isoformat() if w.pk else None,
             "reset_at": w.ends_at.isoformat() if w.pk else None,
             "duration_seconds": 18000 if w.kind == "short" else 604800,
             "policy_version": w.policy_id}
            for w in selected
        ],
    }


@transaction.atomic
def start(user, attempt_key, input_digest, client_capabilities=None, required_scenes=None):
    lock_account(user)
    existing = ProductionTask.objects.filter(account=user, attempt_key=attempt_key).first()
    if existing:
        if existing.input_digest != input_digest:
            raise APIError("本次制作参数已改变，请重新开始", code=40901, status_code=409)
        if client_capabilities is not None:
            from ai_runtime.models import Binding
            binding = Binding.objects.filter(task=existing).first()
            if not binding or sorted(binding.required_scenes) != sorted(required_scenes or []):
                raise APIError("任务配置参数已改变，请结束旧任务后重新制作", status_code=409)
        return existing
    from django.conf import settings
    from ai_runtime.contracts import fail
    runtime_release = None
    if client_capabilities is not None:
        from ai_runtime.services import resolve
        runtime_release = resolve(client_capabilities, required_scenes)
    elif required_scenes is not None or settings.AI_RUNTIME_REQUIRE_CAPABILITIES:
        fail("UPGRADE_REQUIRED", "请更新客户端后开始制作", 426)
    now = timezone.now()
    expire(user, now)
    if ProductionTask.objects.filter(account=user, created_at__gt=now - timedelta(hours=5)).count() >= 30:
        raise APIError("制作尝试过于频繁，请稍后再试", code=42902, status_code=429)
    policy = policy_at(now)
    short, weekly = reserve(user, now, policy)
    task = ProductionTask.objects.create(
        account=user, attempt_key=attempt_key, input_digest=input_digest,
        short_window=short, weekly_window=weekly,
        expires_at=now + timedelta(hours=policy.hold_hours),
    )
    if runtime_release:
        from ai_runtime.models import Binding
        Binding.objects.create(task=task, release=runtime_release,
                               required_scenes=required_scenes, capabilities=client_capabilities)
    record(task, "reserve", user)
    return task


@transaction.atomic
def transition(user, task_id, action, version):
    lock_account(user)
    task = ProductionTask.objects.filter(account=user, pk=task_id).select_related(
        "short_window", "weekly_window",
    ).first()
    if task is None:
        raise APIError("制作任务不存在", status_code=404)
    # Idempotent terminal operations are safe even when the previous response was lost.
    if action == "cancel" and task.state == "cancelled":
        return task
    if task.version != version:
        raise APIError("任务状态已更新，请刷新后继续", code=40902, status_code=409)
    now = timezone.now()
    if task.state in ("reserved", "paused") and task.expires_at <= now:
        release(task, "expired", reason="预占到期")
    if action == "cancel" and task.state in ("reserved", "paused"):
        release(task, "cancelled", user, "用户结束制作")
    elif action == "cancel" and task.state == "expired":
        task.state = "cancelled"
        task.version += 1
        task.save()
    elif action == "pause" and task.state == "reserved":
        task.state = "paused"
        task.expires_at = now + timedelta(hours=task.short_window.policy.hold_hours)
        task.version += 1
        task.save()
    elif action == "resume" and task.state == "expired":
        from ai_runtime.models import Binding
        from ai_runtime.services import channel, enforce_control
        binding = Binding.objects.filter(task=task).select_related("release").first()
        if binding:
            enforce_control(channel(lock=True), binding.release.snapshot, binding.required_scenes)
        policy = policy_at(now)
        short, weekly = reserve(user, now, policy)
        task.short_window, task.weekly_window = short, weekly
        task.reservation_id = uuid.uuid4()
        task.state = "reserved"
        task.expires_at = now + timedelta(hours=policy.hold_hours)
        task.version += 1
        task.save()
        record(task, "reserve", user)
    elif action == "resume" and task.state == "paused":
        task.state = "reserved"
        task.version += 1
        task.save()
    elif not (action == "resume" and task.state == "reserved") and not (
        action == "pause" and task.state == "paused"
    ):
        raise APIError("当前任务不能执行此操作", code=40903, status_code=409)
    return task


@transaction.atomic
def settle_verified_result(user, task_id, verified_result):
    """Called by the trusted result-verification worker, never by a client claim."""
    lock_account(user)
    task = ProductionTask.objects.select_related("short_window", "weekly_window").get(
        account=user, pk=task_id,
    )
    if task.state == "completed":
        if task.result != verified_result and (not verified_result.get("digest") or task.result.get("digest") != verified_result.get("digest")):
            raise APIError("成果已结算", status_code=409)
        return task
    if task.state not in ("reserved", "paused"):
        raise APIError("任务已结束", status_code=409)
    for window in (task.short_window, task.weekly_window):
        window.reserved -= 1
        window.used += 1
        window.save(update_fields=["reserved", "used"])
    task.state = "completed"
    task.result = verified_result
    task.version += 1
    task.save()
    record(task, "settle", user)
    return task


@transaction.atomic
def refund(actor, task_id, reason):
    target = ProductionTask.objects.get(pk=task_id)
    lock_account(target.account)
    task = ProductionTask.objects.select_related("short_window", "weekly_window").get(pk=task_id)
    if ProductionLedger.objects.filter(reservation_id=task.reservation_id, event="refund").exists():
        return task
    if task.state != "completed":
        raise APIError("仅已结算任务可以退回次数", status_code=409)
    for window in (task.short_window, task.weekly_window):
        window.used -= 1
        window.save(update_fields=["used"])
    record(task, "refund", actor, reason)
    return task


@transaction.atomic
def reset_quota(actor, user, request_key, scope, reason):
    from .models import ProductionQuotaReset

    lock_account(user)
    existing = ProductionQuotaReset.objects.filter(request_key=request_key).first()
    if existing:
        if (existing.account_id, existing.scope, existing.reason) != (user.pk, scope, reason):
            raise APIError("重置请求内容已改变，请重新操作", status_code=409)
        return existing
    now = timezone.now()
    kinds = ["short", "weekly"] if scope == "both" else [scope]
    snapshots = []
    active = ProductionWindow.objects.filter(
        account=user, kind__in=kinds, starts_at__lte=now, ends_at__gt=now,
    ).order_by("kind", "pk")
    for window in active:
        snapshots.append({
            "id": window.pk, "kind": window.kind, "starts_at": window.starts_at.isoformat(),
            "previous_ends_at": window.ends_at.isoformat(), "used": window.used,
            "reserved": window.reserved, "limit": window.limit,
        })
        # Existing tasks retain these windows; completion/release remains on the original ledger.
        window.ends_at = now
        window.save(update_fields=["ends_at"])
    return ProductionQuotaReset.objects.create(
        account=user, request_key=request_key, scope=scope, reason=reason,
        actor=actor, windows=snapshots,
    )
