from __future__ import annotations

from django.conf import settings

from ai_config.models import AIModelCatalog, AIProviderKeyConfig, AIScenarioModelBinding, ScenarioKey

from .exceptions import LLMConfigError
from .openai_compatible import OpenAICompatibleGateway
from .types import ProviderRoute


def resolve_chat_route() -> ProviderRoute:
    binding = (
        AIScenarioModelBinding.objects.select_related("model")
        .filter(scenario=ScenarioKey.CHAT, is_active=True, model__is_active=True, model__supports_text=True)
        .order_by("-is_default", "position", "id")
        .first()
    )
    if binding is None:
        raise LLMConfigError("no active chat model binding")
    provider = (
        AIProviderKeyConfig.objects.filter(kind=AIProviderKeyConfig.Kind.API, company=binding.model.company, is_active=True)
        .order_by("-is_using", "position", "id")
        .first()
    )
    if provider is None or not provider.key or not provider.request_url:
        raise LLMConfigError("no active provider credential")
    if not getattr(settings, "DEBUG", False) and not provider.request_url.lower().startswith("https://"):
        raise LLMConfigError("provider endpoint must use https")
    return ProviderRoute(
        provider=provider.company,
        model=binding.model.name,
        endpoint=provider.request_url,
        api_key=provider.key,
        config_version=str(binding.updated_at.isoformat()),
        temperature=binding.temperature,
        max_tokens=binding.max_tokens,
        supports_tool_use=bool(binding.model.supports_tool_use),
        supports_parallel_tool_calls=bool(getattr(binding.model, "supports_tool_use", False)),
    )


def create_chat_gateway(route: ProviderRoute) -> OpenAICompatibleGateway:
    return OpenAICompatibleGateway(
        route,
        connect_timeout=getattr(settings, "CHAT_AI_PROVIDER_CONNECT_TIMEOUT_SECONDS", 10),
        first_event_timeout=getattr(settings, "CHAT_AI_PROVIDER_FIRST_EVENT_TIMEOUT_SECONDS", 30),
        idle_timeout=getattr(settings, "CHAT_AI_PROVIDER_STREAM_IDLE_TIMEOUT_SECONDS", 30),
        max_output_chars=getattr(settings, "CHAT_AI_MAX_OUTPUT_CHARS", 100000),
    )
