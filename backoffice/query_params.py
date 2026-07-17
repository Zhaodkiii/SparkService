"""后台列表查询参数解析。"""

from __future__ import annotations

from django.utils import timezone
from django.utils.dateparse import parse_datetime


class InvalidAdminDatetimeParam(ValueError):
    def __init__(self, field: str):
        super().__init__(field)
        self.field = field


def parse_admin_datetime_param(request, name: str):
    """解析可选 datetime 查询参数；空字符串视为未传；非法值抛 InvalidAdminDatetimeParam。"""
    raw = request.query_params.get(name)
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    parsed = parse_datetime(text)
    if parsed is None:
        raise InvalidAdminDatetimeParam(name)
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed
