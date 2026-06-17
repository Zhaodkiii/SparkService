"""计划级本机提醒授权：服务端统一管理非本人服药计划的本地提醒资格。"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.models import User

from medical.models import MedicationPlan, MedicationReminderLocalAuthorization
from medical.services.member_binding_service import get_active_binding


@dataclass(frozen=True)
class MedicationReminderAuthorizationContext:
    plan: MedicationPlan
    binding_relationship: str
    is_self_member: bool
    authorization: MedicationReminderLocalAuthorization | None


def load_authorization_context(*, user: User, plan_id: int) -> MedicationReminderAuthorizationContext:
    plan = (
        MedicationPlan.objects.select_related("member")
        .filter(id=plan_id, is_deleted=False, member__is_deleted=False)
        .first()
    )
    if plan is None:
        raise MedicationPlan.DoesNotExist

    binding = get_active_binding(user=user, member_id=plan.member_id)
    if binding is None:
        raise PermissionError("permission_denied")

    authorization = (
        MedicationReminderLocalAuthorization.objects.filter(
            user=user,
            medication_plan_id=plan.id,
        )
        .select_related("member", "medication_plan")
        .first()
    )
    return MedicationReminderAuthorizationContext(
        plan=plan,
        binding_relationship=binding.relationship,
        is_self_member=binding.relationship == "self",
        authorization=authorization,
    )


def serialize_authorization_context(
    *,
    user: User,
    context: MedicationReminderAuthorizationContext,
) -> dict:
    authorization = context.authorization
    if context.is_self_member:
        enabled = True
        exists = authorization is not None
        source = authorization.source if authorization else "self_member"
        updated_at = authorization.updated_at.isoformat() if authorization else None
        identifier = authorization.id if authorization else None
    else:
        enabled = bool(authorization and authorization.enabled)
        exists = authorization is not None
        source = authorization.source if authorization else ""
        updated_at = authorization.updated_at.isoformat() if authorization else None
        identifier = authorization.id if authorization else None

    return {
        "id": identifier,
        "user_id": user.id,
        "member_id": context.plan.member_id,
        "medication_plan_id": context.plan.id,
        "enabled": enabled,
        "exists": exists,
        "is_self_member": context.is_self_member,
        "source": source,
        "updated_at": updated_at,
    }


def upsert_local_authorization(
    *,
    user: User,
    plan_id: int,
    enabled: bool,
    source: str,
) -> dict:
    """
    新增/更新本机服药提醒授权记录（幂等upsert逻辑）
    仅针对非本人成员的服药计划生效；本人计划直接返回原有上下文，不生成授权记录
    前置校验：服药计划必须为启用提醒+正常生效状态，否则抛出参数异常

    Args:
        user: 当前登录操作用户
        plan_id: 目标服药计划ID
        enabled: 是否开启本机本地通知授权
        source: 操作来源标识（页面/模块，用于日志追溯）

    Returns:
        dict: 序列化后的授权完整上下文数据，返回给前端

    Raises:
        ValueError: 服药计划未开启提醒 或 计划状态非ACTIVE生效中
    """
    # 加载权限上下文，校验用户是否有权访问该服药计划
    context = load_authorization_context(user=user, plan_id=plan_id)
    plan = context.plan

    # 校验计划基础状态：必须开启提醒且为生效中，不满足则拒绝操作
    if not plan.reminder_enabled or plan.status != MedicationPlan.Status.ACTIVE:
        raise ValueError("invalid_plan_reminder_state")

    # 如果是本人的服药计划，无需创建授权，直接返回原始上下文
    if context.is_self_member:
        return serialize_authorization_context(user=user, context=context)

    # 查询或创建授权记录：用户+服药计划 联合唯一约束
    authorization, created = MedicationReminderLocalAuthorization.objects.get_or_create(
        user=user,
        medication_plan=plan,
        defaults={
            "member": plan.member,    # 计划所属成员
            "enabled": enabled,       # 本机通知开关状态
            "source": source,         # 操作来源标记
        },
    )

    # 记录已存在：执行更新，仅修改指定字段
    if not created:
        authorization.member = plan.member
        authorization.enabled = enabled
        authorization.source = source
        # 仅更新业务字段与更新时间，减少数据库写入
        authorization.save(update_fields=["member", "enabled", "source", "updated_at"])

    # 刷新上下文，绑定最新的授权记录
    refreshed = MedicationReminderAuthorizationContext(
        plan=plan,
        binding_relationship=context.binding_relationship,
        is_self_member=False,
        authorization=authorization,
    )
    # 序列化为前端返回JSON结构
    return serialize_authorization_context(user=user, context=refreshed)


def disable_local_authorization(*, user: User, plan_id: int) -> dict:
    """
    关闭本机服药提醒授权（软关闭，不删除数据库记录）
    逻辑：仅当存在授权且开关为开启时，才置为关闭并更新时间

    Args:
        user: 当前登录操作用户
        plan_id: 目标服药计划ID

    Returns:
        dict: 更新后的授权上下文序列化数据
    """
    # 加载计划与权限上下文，校验访问权限
    context = load_authorization_context(user=user, plan_id=plan_id)
    authorization = context.authorization

    # 存在授权记录且当前为开启状态时，执行关闭操作
    if authorization is not None and authorization.enabled:
        authorization.enabled = False
        # 更新开关与最后修改时间
        authorization.save(update_fields=["enabled", "updated_at"])
        # 重新构建上下文，携带更新后的授权对象
        context = MedicationReminderAuthorizationContext(
            plan=context.plan,
            binding_relationship=context.binding_relationship,
            is_self_member=context.is_self_member,
            authorization=authorization,
        )
    # 序列化返回最新状态
    return serialize_authorization_context(user=user, context=context)