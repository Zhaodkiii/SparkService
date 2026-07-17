"""后台列表统一排序解析。

页面只声明白名单字段与默认排序，不在各自 View 中散落 if/else。
"""

from __future__ import annotations

from typing import Any


def resolve_admin_sort(
    request,
    *,
    allowed: dict[str, dict[str, list[Any]]],
    default: tuple[str, str],
) -> list[Any]:
    """解析 `sort_by` / `order`，返回可直接传入 `QuerySet.order_by(*...)` 的列表。

    - `sort_by` 不在白名单、或 `order` 不是 asc/desc：回退默认排序
    - 白名单内每个字段必须提供 `asc` / `desc` 对应的稳定 order_by 列表
    """
    default_field, default_order = default
    sort_by = (request.query_params.get("sort_by") or "").strip()
    order = (request.query_params.get("order") or "").strip().lower()

    if sort_by not in allowed or order not in {"asc", "desc"}:
        sort_by = default_field
        order = default_order if default_order in {"asc", "desc"} else "desc"

    field_orders = allowed.get(sort_by) or {}
    order_by = field_orders.get(order)
    if not order_by:
        fallback = allowed.get(default_field) or {}
        order_by = fallback.get(default_order if default_order in {"asc", "desc"} else "desc")
    if not order_by:
        # 最后兜底：保证永远可排序
        return ["-id"]
    return list(order_by)
