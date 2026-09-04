"""AI Provider 解析共享工具。

供通用 Pro bootstrap（ai_config.views）与医院医生智能体专用运行配置
（hospital_care.api.patient.views）复用，保证两端按同一规则解析
endpoint 与 api_key。
"""

from __future__ import annotations

from ai_config.models import AIProviderKeyConfig


def load_active_api_providers() -> list[AIProviderKeyConfig]:
    """当前生效的 API 类型 Provider 配置（优先 is_using，再按 position）。"""
    return list(
        AIProviderKeyConfig.objects.filter(kind=AIProviderKeyConfig.Kind.API, is_active=True).order_by(
            "-is_using", "position", "company", "name"
        )
    )


def build_provider_index(provider_rows) -> dict[str, AIProviderKeyConfig]:
    """每个厂商只选一个“当前生效 provider”（优先 is_using，再按 position）。"""
    provider_by_company: dict[str, AIProviderKeyConfig] = {}
    for row in provider_rows:
        normalized_company = str(row.company or "").strip().upper()
        if not normalized_company:
            continue
        if normalized_company not in provider_by_company:
            provider_by_company[normalized_company] = row
    return provider_by_company


def resolve_provider_for_model(company: str, provider_by_company: dict) -> dict | None:
    """根据模型所属厂商解析 provider 配置（endpoint 和 api_key）。"""
    normalized_company = str(company or "").strip().upper()
    if not normalized_company:
        return None

    provider = provider_by_company.get(normalized_company)
    if provider is None:
        return None

    return {
        "endpoint": provider.request_url or "",
        "api_key": provider.key or "",
    }
