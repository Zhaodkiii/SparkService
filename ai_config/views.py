from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from ai_config.defaults import (
    DEFAULT_API_KEYS,
    DEFAULT_MODELS,
    DEFAULT_SCENARIOS,
    DEFAULT_SEARCH_KEYS,
    DEFAULT_TOOL_KEYS,
    DEFAULT_USER_INFO,
)
from ai_config.models import AIBootstrapProfile, AIModelCatalog, AIProviderKeyConfig, AIScenarioConfig
from common.response import success_response


class AIBootstrapConfigView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        scenarios = self._build_scenarios()
        api_keys = self._build_provider_keys(AIProviderKeyConfig.Kind.API, DEFAULT_API_KEYS, payload_key="api")
        search_keys = self._build_provider_keys(AIProviderKeyConfig.Kind.SEARCH, DEFAULT_SEARCH_KEYS, payload_key="search")
        tool_keys = self._build_provider_keys(AIProviderKeyConfig.Kind.TOOL, DEFAULT_TOOL_KEYS, payload_key="tool")
        models = self._build_models()
        user_info = self._build_user_info()

        revision = self._resolve_revision()
        payload = {
            "revision": revision,
            "scenarios": scenarios,
            "api_keys": api_keys,
            "search_keys": search_keys,
            "tool_keys": tool_keys,
            "all_models": models,
            "user_info": user_info,
        }
        return success_response(payload, msg="ok", code=0)

    def _build_scenarios(self):
        rows = AIScenarioConfig.objects.filter(is_active=True)
        if rows.exists() is False:
            return DEFAULT_SCENARIOS

        payload = dict(DEFAULT_SCENARIOS)
        for row in rows:
            payload[row.scenario] = {
                "endpoint": row.endpoint,
                "model": row.model,
                "api_key": row.api_key,
                "temperature": row.temperature,
                "max_tokens": row.max_tokens,
            }
        return payload

    def _build_provider_keys(self, kind, default_payload, payload_key: str):
        rows = AIProviderKeyConfig.objects.filter(kind=kind, is_active=True).order_by("position", "company", "name")
        if rows.exists() is False:
            return default_payload

        result = []
        for row in rows:
            item = {
                "name": row.name,
                "company": row.company,
                "key": row.key,
                "request_url": row.request_url,
                "is_hidden": row.is_hidden,
                "help": row.help,
                "source": row.source,
            }
            if payload_key == "search":
                item["is_using"] = row.is_using
                item["search_class"] = row.capability_class or "web"
            if payload_key == "tool":
                item["is_using"] = row.is_using
                item["tool_class"] = row.capability_class or "native"
            result.append(item)
        return result

    def _build_models(self):
        rows = AIModelCatalog.objects.filter(is_active=True).order_by("position", "name")
        if rows.exists() is False:
            return DEFAULT_MODELS

        return [
            {
                "name": row.name,
                "display_name": row.display_name,
                "identity": row.identity,
                "position": row.position,
                "company": row.company,
                "is_hidden": row.is_hidden,
                "supports_search": row.supports_search,
                "supports_multimodal": row.supports_multimodal,
                "supports_reasoning": row.supports_reasoning,
                "supports_tool_use": row.supports_tool_use,
                "supports_voice_gen": row.supports_voice_gen,
                "supports_image_gen": row.supports_image_gen,
                "source": row.source,
            }
            for row in rows
        ]

    def _build_user_info(self):
        profile = AIBootstrapProfile.objects.order_by("-updated_at").first()
        if profile is None:
            return DEFAULT_USER_INFO
        return {
            "choose_embedding_model": profile.choose_embedding_model,
            "optimization_text_model": profile.optimization_text_model,
            "optimization_visual_model": profile.optimization_visual_model,
            "text_to_speech_model": profile.text_to_speech_model,
            "use_knowledge": profile.use_knowledge,
            "knowledge_count": profile.knowledge_count,
            "knowledge_similarity": profile.knowledge_similarity,
            "use_search": profile.use_search,
            "bilingual_search": profile.bilingual_search,
            "search_count": profile.search_count,
            "use_map": profile.use_map,
            "use_calendar": profile.use_calendar,
            "use_weather": profile.use_weather,
            "use_canvas": profile.use_canvas,
            "use_code": profile.use_code,
        }

    def _resolve_revision(self):
        points = [
            AIScenarioConfig.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
            AIProviderKeyConfig.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
            AIModelCatalog.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
            AIBootstrapProfile.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
        ]
        points = [point for point in points if point is not None]
        if not points:
            return timezone.now().isoformat()
        return max(points).isoformat()
