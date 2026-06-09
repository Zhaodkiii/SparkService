"""成员边界工具。"""

from django.contrib.auth.models import User

from medical.models import Member


def is_self_primary_member(user: User, member_id: int) -> bool:
    return Member.objects.filter(id=member_id, user=user, is_primary=True, is_deleted=False).exists()
