from datetime import timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from common.exceptions import APIError
from ai_runtime.contracts import digest
from .entitlements import entitlement, identity_for_account
from .models import (
    ProductionCall, ProductionControl, ProductionLedger, ProductionPolicy, ProductionQuotaReset,
    ProductionTask, ProductionWindow,
)

PRECISION = Decimal("0.000001")
WINDOWS = (("short", 5), ("weekly", 168))


def lock_account(user):
    get_user_model().objects.select_for_update().get(pk=user.pk)


def current_policy(now):
    return ProductionPolicy.objects.filter(effective_at__lte=now).order_by("-effective_at", "-pk").first()


def accepting(policy):
    return bool(policy and policy.enabled and not ProductionControl.objects.filter(pk=1, accepting=False).exists())


def limit_for(policy, kind, plan):
    if kind == "short":
        return policy.short_limit_points
    return policy.weekly_limit_points if plan == "pro" else policy.free_weekly_limit_points


def windows(user, now, policy, plan):
    selected = {}
    for kind, hours in WINDOWS:
        if kind == "short" and plan != "pro":
            continue
        window = (ProductionWindow.objects.filter(account=user, kind=kind, starts_at__lte=now, ends_at__gt=now)
                  .select_related("policy").order_by("-starts_at", "-pk").first())
        if window is None:
            window = ProductionWindow(account=user, kind=kind, starts_at=now, ends_at=now + timedelta(hours=hours),
                                      limit_points=limit_for(policy, kind, plan), policy=policy)
        selected[kind] = window
    return selected


def remaining(window, limit):
    return max(Decimal(0), limit - window.used_points)


def quota(user, *, admin=False, identity=None, now=None):
    now = now or timezone.now()
    policy = current_policy(now)
    identity = identity if identity is not None else identity_for_account(user)
    plan, membership = entitlement(identity, now)
    active = windows(user, now, policy, plan) if policy and plan else {}
    pending = ProductionCall.objects.filter(task__account=user, accounting_state="pending").exists()
    items = []
    for w in active.values():
        limit = limit_for(w.policy, w.kind, plan)
        balance = remaining(w, limit)
        status = "active" if w.pk else (
            "awaiting_first_use" if ProductionWindow.objects.filter(account=user, kind=w.kind).exists() else "not_started"
        )
        item = dict(kind=w.kind, status=status, remaining_ratio=float(balance / limit) if limit else 0,
                    starts_at=w.starts_at.isoformat() if w.pk else None, reset_at=w.ends_at.isoformat() if w.pk else None,
                    duration_seconds=dict(WINDOWS)[w.kind] * 3600, window_policy_version=w.policy_id)
        if admin:
            item.update(limit_points=str(limit), used_points=str(w.used_points), remaining_points=str(balance))
        items.append(item)
    return dict(server_time=now.isoformat(), policy_version=policy.pk if policy else 0, windows=items,
                plan=plan, entitlement_state="verified" if plan else "unavailable",
                membership_expires_at=membership.active_until if membership else None,
                membership_verified_at=membership.verified_at if membership else None,
                pending_usage=pending, entitled=user.is_active,
                service_status="available" if accepting(policy) else "maintenance" if policy else "unconfigured")


@transaction.atomic
def start(user, attempt_key, input_digest, client_capabilities, required_scenes):
    from ai_runtime.models import Binding
    from ai_runtime.services import resolve

    lock_account(user)
    existing = ProductionTask.objects.filter(account=user, attempt_key=attempt_key).first()
    if existing:
        binding = Binding.objects.filter(task=existing).first()
        if existing.input_digest != input_digest or not binding or set(binding.required_scenes) != set(required_scenes):
            raise APIError("制作请求内容已改变", status_code=409)
        return existing

    release = resolve(client_capabilities, required_scenes)
    task = ProductionTask.objects.create(account=user, attempt_key=attempt_key, input_digest=input_digest)
    Binding.objects.create(task=task, release=release, required_scenes=required_scenes, capabilities=client_capabilities)
    return task


def get_task(user, task_id):
    task = ProductionTask.objects.filter(account=user, pk=task_id).first()
    if not task:
        raise APIError("制作任务不存在", status_code=404)
    return task


@transaction.atomic
def transition(user, task_id, action, version):
    lock_account(user)
    task = get_task(user, task_id)
    states = {"resume": "ready", "pause": "paused", "cancel": "cancelled"}
    target = states[action]
    if task.state == target:
        return task
    if task.version != version or task.state not in ("ready", "paused"):
        raise APIError("请刷新制作任务状态", status_code=409)
    task.state = target
    task.version += 1
    task.save(update_fields=["state", "version", "updated_at"])
    return task


@transaction.atomic
def complete(user, task_id, result):
    lock_account(user)
    task = get_task(user, task_id)
    if task.state == "completed" and task.result == result:
        return task
    if task.state not in ("ready", "paused") or not task.calls.exists():
        raise APIError("当前制作无法记录成果", status_code=409)
    task.state = "completed"
    task.completed_at = timezone.now()
    task.result = result
    task.version += 1
    task.save()
    return task


def points(rate, usage, parameters):
    if rate["mode"] == "images":
        count = usage.get("generated_images")
        if count is None:
            return None
        return Decimal(rate["image_rates"][parameters["size"]]) * count

    input_tokens = usage.get("input_tokens", 0 if rate["category"] == "image_ai" else None)
    output_tokens = usage.get("output_tokens")
    cached = usage.get("cached_input_tokens", 0)
    if input_tokens is None or output_tokens is None or cached > input_tokens:
        return None
    return ((input_tokens - cached) * Decimal(rate["input_rate"]) + cached * Decimal(rate["cached_input_rate"])
            + output_tokens * Decimal(rate["output_rate"])) / 1000


@transaction.atomic
def authorize(user, task_id, call_id, scene, input_digest, parameters, *, identity=None):
    from ai_runtime.models import Binding
    from ai_runtime.services import channel, enforce_control

    lock_account(user)
    task = get_task(user, task_id)
    existing = ProductionCall.objects.filter(pk=call_id).first()
    if existing:
        if (existing.task_id, existing.scene, existing.input_digest, existing.parameters) != (task.pk, scene, input_digest, parameters):
            raise APIError("调用请求内容已改变", status_code=409)
        return existing
    now = timezone.now()
    ProductionControl.objects.select_for_update().get(pk=1)
    policy = current_policy(timezone.now())
    if not user.is_active or not accepting(policy):
        raise APIError("AI 制作暂不可用", status_code=503)
    if task.state != "ready":
        raise APIError("请先恢复制作任务", status_code=409)
    if ProductionCall.objects.filter(task__account=user, created_at__gt=now - timedelta(minutes=1)).count() >= 30:
        raise APIError("调用过于频繁，请稍后重试", status_code=429,
                       details={"error_key": "RATE_LIMITED", "retry_after_seconds": 60})
    binding = Binding.objects.select_related("release").filter(task=task).first()
    if not binding or scene not in binding.required_scenes:
        raise APIError("未授权的模型场景", status_code=403)
    snapshot = binding.release.snapshot
    enforce_control(channel(lock=True), snapshot, [scene])
    config = snapshot["scenes"][scene]
    model = config["model_id"]
    category = "image_ai" if config["adapter_id"] == "ark_images_v1" else "text_ai"
    rate = policy.rates.get(model)
    if not rate or rate["category"] != category:
        raise APIError("模型用量策略尚未配置", status_code=503, details={"error_key": "PRICING_UNCONFIGURED"})
    expire_calls(user)
    if ProductionCall.objects.filter(task__account=user, accounting_state="pending").exists():
        raise APIError("当前账号有调用处理中", status_code=409, details={"error_key": "CALL_IN_PROGRESS"})
    if category == "image_ai":
        size = parameters.get("size")
        if not isinstance(size, str):
            raise APIError("图片规格无效")
        if size not in rate["image_rates"] or size != config["parameters"].get("size", "2K"):
            raise APIError("图片规格未配置")
    else:
        limit = parameters.get("max_output_tokens")
        configured_limit = config["parameters"].get("max_output_tokens")
        if type(limit) is not int or not 1 <= limit <= rate["max_output_tokens"] or (configured_limit and limit != configured_limit):
            raise APIError("最大输出 token 超出模型策略")
    budget = call_budget(rate, parameters)
    identity = identity if identity is not None else identity_for_account(user)
    plan, membership = entitlement(identity, lock=True)
    if not plan:
        raise APIError("会员状态暂时无法确认，请重试", status_code=503,
                       details={"error_key": "MEMBERSHIP_UNAVAILABLE"})
    now = timezone.now()
    selected = windows(user, now, policy, plan)
    blocked = [w for w in selected.values() if remaining(w, limit_for(w.policy, w.kind, plan)) < budget]
    if blocked:
        if any(limit_for(w.policy, w.kind, plan) < budget and limit_for(policy, w.kind, plan) < budget
               for w in blocked):
            raise APIError("单次调用所需额度超过周期上限，请调整请求", status_code=422,
                           details={"error_key": "CALL_BUDGET_EXCEEDS_LIMIT"})
        reset = max(w.ends_at for w in blocked).isoformat() if all(
            w.pk and limit_for(policy, w.kind, plan) >= budget for w in blocked) else None
        raise APIError("制作额度不足", status_code=429, details={
            "error_key": "QUOTA_INSUFFICIENT", "plan": plan, "blocked_windows": [w.kind for w in blocked],
            "next_eligible_at": reset,
        })
    for window in selected.values():
        if not window.pk:
            window.save()
    return ProductionCall.objects.create(
        id=call_id, task=task, scene=scene, model=model, category=category, input_digest=input_digest,
        parameters=parameters, policy=policy, rate=rate, budget=budget, short_window=selected.get("short"),
        plan_at_authorization=plan, membership_verified_at=membership.verified_at if membership else None,
        weekly_window=selected["weekly"], usage_due_at=now + timedelta(seconds=rate["usage_timeout_seconds"]),
    )


def call_budget(rate, parameters):
    if rate["mode"] == "images":
        budget = points(rate, {"generated_images": rate["max_images"]}, {"size": parameters.get("size", "2K")})
    else:
        output_limit = rate["max_output_tokens"]
        if rate["category"] == "text_ai":
            output_limit = parameters.get("max_output_tokens") or output_limit
        budget = token_budget(rate, output_limit)
    return max(budget, Decimal(rate["minimum_charge"])).quantize(PRECISION, rounding=ROUND_CEILING)


def token_budget(rate, output_limit):
    input_rate = max(Decimal(rate["input_rate"]), Decimal(rate["cached_input_rate"]))
    return (rate["max_input_tokens"] * input_rate + output_limit * Decimal(rate["output_rate"])) / 1000


def get_call(user, task_id, call_id):
    call = ProductionCall.objects.filter(task__account=user, task_id=task_id, pk=call_id).first()
    if not call:
        raise APIError("模型调用不存在", status_code=404, details={"error_key": "CALL_NOT_FOUND"})
    return call


def write_usage(call, event_id, usage, source, execution_state, provider_request_id="", reason=""):
    fingerprint = digest([str(call.pk), usage, source, execution_state, provider_request_id, reason])
    previous = ProductionLedger.objects.filter(event_id=event_id).first()
    if previous:
        if previous.payload_digest != fingerprint:
            raise APIError("用量事件内容已改变", status_code=409)
        return call
    charge = points(call.rate, usage, call.parameters)
    if charge is None:
        if source != "estimated":
            raise APIError("用量字段不完整")
        charge = Decimal(call.rate["minimum_charge"])
    if not charge and execution_state in ("failed", "cancelled"):
        charge = Decimal(call.rate["minimum_charge"])
    charge = charge.quantize(PRECISION, rounding=ROUND_HALF_UP)
    delta = charge - call.charged_points
    event = "charge" if call.accounting_state == "pending" else "measurement_adjustment"
    ProductionWindow.objects.filter(pk__in=[call.short_window_id, call.weekly_window_id]).update(
        used_points=F("used_points") + delta,
    )
    ProductionLedger.objects.create(call=call, event_id=event_id, payload_digest=fingerprint, event=event,
                                    delta_points=delta, resulting_points=charge, usage_source=source, reason=reason)
    call.accounting_state = "estimated" if source == "estimated" else "actual"
    call.charged_points = charge
    call.execution_state = execution_state
    call.usage_source = source
    call.usage = usage
    call.provider_request_id = provider_request_id or call.provider_request_id
    call.version += 1
    call.save()
    return call


@transaction.atomic
def report(user, task_id, call_id, event_id, execution_state, usage, provider_request_id):
    lock_account(user)
    call = get_call(user, task_id, call_id)
    if provider_request_id and ProductionCall.objects.filter(
        task__account=user, model=call.model, provider_request_id=provider_request_id,
    ).exclude(pk=call.pk).exists():
        raise APIError("供应商请求已记录", status_code=409)
    if points(call.rate, usage, call.parameters) is None:
        if call.accounting_state == "pending" and execution_state in ("failed", "cancelled"):
            return write_usage(call, event_id, {}, "estimated", execution_state, provider_request_id, "调用未返回用量")
        if call.accounting_state == "pending":
            call.execution_state = execution_state
            call.provider_request_id = provider_request_id
            call.save(update_fields=["execution_state", "provider_request_id"])
        return call
    if call.accounting_state == "actual":
        if call.usage_source == "admin_verified" or call.usage == usage:
            return call
        raise APIError("用量已入账", status_code=409)
    return write_usage(call, event_id, usage, "client_reported", execution_state, provider_request_id)


def expire_calls(user):
    expired = ProductionCall.objects.filter(task__account=user, accounting_state="pending", usage_due_at__lte=timezone.now())
    for call in expired:
        write_usage(call, uuid.uuid4(), {}, "estimated", call.execution_state, reason="用量等待超时")


@transaction.atomic
def expire_account_calls(user):
    lock_account(user)
    expire_calls(user)


@transaction.atomic
def adjust(call_id, request_key, version, usage, reason):
    target = ProductionCall.objects.select_related("task__account").filter(pk=call_id).first()
    if not target:
        raise APIError("模型调用不存在", status_code=404)
    user = target.task.account
    lock_account(user)
    call = get_call(user, target.task_id, call_id)
    if not ProductionLedger.objects.filter(event_id=request_key).exists() and call.version != version:
        raise APIError("用量记录已更新，请刷新", status_code=409)
    return write_usage(call, request_key, usage, "admin_verified", call.execution_state, reason=reason)


@transaction.atomic
def reset_quota(actor, user, request_key, scope, reason, expected_plan=None):
    lock_account(user)
    reset = ProductionQuotaReset.objects.filter(request_key=request_key).first()
    if reset:
        if (reset.account_id, reset.scope, reset.reason) != (user.pk, scope, reason):
            raise APIError("重置请求内容已改变", status_code=409)
        return reset
    now = timezone.now()
    plan, _ = entitlement(identity_for_account(user), lock=True)
    if not plan or (expected_plan and plan != expected_plan) or (plan == "free" and scope != "weekly"):
        raise APIError("会员等级或可重置周期已变化，请刷新", status_code=409)
    expire_calls(user)
    if ProductionCall.objects.filter(task__account=user, accounting_state="pending").exists():
        raise APIError("有调用待记账，请稍后重试", status_code=409)
    kinds = ["short", "weekly"] if scope == "both" else [scope]
    selected = ProductionWindow.objects.filter(account=user, kind__in=kinds, starts_at__lte=now, ends_at__gt=now)
    snapshots = []
    for w in selected:
        snapshots.append(dict(id=w.pk, kind=w.kind, used_points=str(w.used_points), limit_points=str(limit_for(w.policy, w.kind, plan)),
                              policy_version=w.policy_id, reset_at=w.ends_at.isoformat()))
        w.ends_at = now
        w.save(update_fields=["ends_at"])
    return ProductionQuotaReset.objects.create(account=user, actor=actor, request_key=request_key,
                                                scope=scope, reason=reason, windows=snapshots, plan=plan)
