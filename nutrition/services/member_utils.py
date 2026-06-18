"""成员边界工具。

营养模块中与 Apple Health 相关的读写（导入外部摄入、回写 UUID 等）仅允许「本人」成员操作。
本模块提供统一的本人判定逻辑，与 iOS 端 `member.isPrimary` 语义对齐。
"""

from django.contrib.auth.models import User

from medical.models import Member, UserMemberBinding


def _normalize_relationship(value: str) -> str:
    """将绑定关系字段标准化：去首尾空白并转小写，便于中英文混存时比较。"""
    return (value or "").strip().lower()


def is_self_primary_member(user: User, member_id: int) -> bool:
    """判断当前登录用户是否以「本人」身份操作指定成员。

    判定顺序（任一满足即视为本人）：
    1. 存在 ACTIVE 的 UserMemberBinding，且 relationship 为 `self` 或 `本人`
    2. 回退：Member 表上 user 匹配且 is_primary=True（兼容旧数据或未走 binding 的场景）

    用途：Apple Health 导入、intake/energy_burn 的 apple_health_id 回写等接口的前置校验。
    家庭成员（子女、父母等）不允许同步 HealthKit 数据，避免隐私与数据串户。
    """
    binding = (
        UserMemberBinding.objects.filter(
            user=user,
            member_id=member_id,
            status=UserMemberBinding.Status.ACTIVE,
            member__is_deleted=False,
        )
        .only("relationship")
        .first()
    )
    if binding is not None:
        return _normalize_relationship(binding.relationship) in {"self", "本人"}

    return Member.objects.filter(id=member_id, user=user, is_primary=True, is_deleted=False).exists()
