"""医疗档案归档查询参数解析与 queryset 过滤。"""

from __future__ import annotations

from rest_framework.exceptions import ValidationError


def parse_archived_param(request) -> str:
    """解析 ``archived`` 查询参数。

    Returns:
        ``"active"`` | ``"archived"`` | ``"all"``
    """
    raw = request.query_params.get("archived")
    if raw is None or raw == "":
        return "active"
    value = str(raw).strip().lower()
    if value in {"false", "0", "no"}:
        return "active"
    if value in {"true", "1", "yes"}:
        return "archived"
    if value == "all":
        return "all"
    raise ValidationError({"archived": "invalid_archived_param"})


def apply_archived_filter(queryset, mode: str):
    """按归档模式过滤 queryset（模型须含 ``is_archived`` 字段）。"""
    if mode == "archived":
        return queryset.filter(is_archived=True)
    if mode == "all":
        return queryset
    return queryset.filter(is_archived=False)


def model_has_is_archived(model) -> bool:
    return any(field.name == "is_archived" for field in model._meta.fields)


def apply_archive_state_to_validated_data(serializer) -> None:
    """在 ``perform_update`` 前根据 ``is_archived`` 同步 ``archived_at``。

    规则：
    - 请求未包含 ``is_archived``：不改动归档字段
    - ``true`` 且当前未归档：写入 ``archived_at=now``
    - ``true`` 且已归档：保持原 ``archived_at``（幂等）
    - ``false``：清空 ``archived_at``
    """
    if "is_archived" not in serializer.validated_data:
        return
    instance = serializer.instance
    if instance is None or not hasattr(instance, "is_archived"):
        return
    new_value = bool(serializer.validated_data["is_archived"])
    if new_value:
        if not instance.is_archived:
            from django.utils import timezone

            serializer.validated_data["archived_at"] = timezone.now()
    else:
        serializer.validated_data["archived_at"] = None
