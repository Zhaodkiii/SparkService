"""SparkService 服务端工具名称枚举。

新增服务端工具时必须先在此枚举登记，再补充 Registry、Schema、Policy、Executor 与测试，
最后才允许后台勾选写入 ``server_tool_scenarios``。

本枚举不收录客户端 ``SparkToolName``（健康、定位、日历、客户端 UI 等）。
枚举只是配置白名单，不代表当前 Run 一定可用。
"""

from __future__ import annotations

from django.db import models


class SparkServerToolName(models.TextChoices):
    ASK_USER = "ask_user", "询问用户"
    SEARCH_KNOWLEDGE_BAG = "search_knowledge_bag", "搜索知识库"
    GET_CURRENT_MEMBER = "get_current_member", "获取当前成员"
    QUERY_MEMBER_PROFILE = "query_member_profile", "查询成员资料"
    LIST_MEMBER_HEALTH_SOURCES = "list_member_health_sources", "检索成员健康资料"
    GET_HEALTH_RESOURCE_CONTEXT = "get_health_resource_context", "获取健康资料解读上下文"
    READ_SOURCE = "read_source", "读取资料"


def server_tool_name_values() -> frozenset[str]:
    return frozenset(item.value for item in SparkServerToolName)


__all__ = ["SparkServerToolName", "server_tool_name_values"]
