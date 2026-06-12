"""
服药记录列表查询：按 scheduled_at 日期区间过滤。

约定：
- scheduled_from：含下界，scheduled_at >= scheduled_from
- scheduled_to：不含上界，scheduled_at < scheduled_to

iOS 客户端 `MedicationRecordScheduledRange` 一次请求覆盖选中日前后 4 天（共 9 天），
`scheduled_to` 传第 5 天 00:00:00，因此必须使用 < 而非 <=。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from django.utils.dateparse import parse_datetime
from django.utils.timezone import get_current_timezone, is_aware, make_aware
from rest_framework import status

from common.response import error_response


@dataclass(frozen=True)
class MedicationRecordScheduledRange:
    start: datetime | None
    end_exclusive: datetime | None


def _parse_scheduled_bound(raw: str) -> datetime | None:
    value = (raw or "").strip()
    if not value:
        return None

    parsed = parse_datetime(value)
    if parsed is None and len(value) >= 10:
        try:
            day = date.fromisoformat(value[:10])
            parsed = datetime.combine(day, time.min)
        except ValueError:
            return None

    if parsed is None:
        return None
    if not is_aware(parsed):
        parsed = make_aware(parsed, get_current_timezone())
    return parsed


def parse_medication_record_scheduled_range(query_params):
    """
    解析 scheduled_from / scheduled_to 查询参数。

    返回 (range, error_response)。error_response 非空时应直接返回给客户端。
    """
    raw_from = query_params.get("scheduled_from")
    raw_to = query_params.get("scheduled_to")
    if raw_from is None and raw_to is None:
        return None, None

    start = _parse_scheduled_bound(raw_from) if raw_from is not None else None
    end_exclusive = _parse_scheduled_bound(raw_to) if raw_to is not None else None

    if raw_from is not None and start is None:
        return None, error_response(
            msg="invalid_scheduled_from",
            code=-1,
            status_code=status.HTTP_400_BAD_REQUEST,
            data={"detail": "Query parameter 'scheduled_from' must be ISO8601 datetime or YYYY-MM-DD."},
        )
    if raw_to is not None and end_exclusive is None:
        return None, error_response(
            msg="invalid_scheduled_to",
            code=-1,
            status_code=status.HTTP_400_BAD_REQUEST,
            data={"detail": "Query parameter 'scheduled_to' must be ISO8601 datetime or YYYY-MM-DD."},
        )
    if start is not None and end_exclusive is not None and start >= end_exclusive:
        return None, error_response(
            msg="invalid_scheduled_range",
            code=-1,
            status_code=status.HTTP_400_BAD_REQUEST,
            data={"detail": "Query parameter 'scheduled_from' must be earlier than 'scheduled_to'."},
        )

    return MedicationRecordScheduledRange(start=start, end_exclusive=end_exclusive), None


def apply_medication_record_scheduled_range(queryset, scheduled_range: MedicationRecordScheduledRange | None):
    if scheduled_range is None:
        return queryset
    if scheduled_range.start is not None:
        queryset = queryset.filter(scheduled_at__gte=scheduled_range.start)
    if scheduled_range.end_exclusive is not None:
        queryset = queryset.filter(scheduled_at__lt=scheduled_range.end_exclusive)
    return queryset
