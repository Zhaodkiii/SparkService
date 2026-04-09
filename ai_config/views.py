from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status
from urllib import request as urllib_request
from urllib import error as urllib_error
import json

from ai_config.defaults import (
    DEFAULT_API_KEYS,
    DEFAULT_MODELS,
    DEFAULT_SCENARIOS,
    DEFAULT_SEARCH_KEYS,
    DEFAULT_TOOL_KEYS,
    DEFAULT_USER_INFO,
)
from ai_config.models import (
    AIBootstrapProfile,
    AIModelCatalog,
    AIProviderKeyConfig,
    AIScenarioModelBinding,
    TrialApplication,
    TrialModelPolicy,
    TrialModelPolicyItem,
)
from ai_config.services import TrialService
from common.response import success_response


class AIBootstrapConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        api_provider_rows = list(
            AIProviderKeyConfig.objects.filter(kind=AIProviderKeyConfig.Kind.API, is_active=True).order_by(
                "-is_using", "position", "company", "name"
            )
        )
        model_rows = list(AIModelCatalog.objects.filter(is_active=True).order_by("position", "name"))
        provider_by_company = self._build_provider_index(api_provider_rows)
        model_company_by_name = {row.name: row.company for row in model_rows}

        scenarios = self._build_scenarios(
            provider_by_company=provider_by_company,
            model_company_by_name=model_company_by_name,
        )
        api_keys = self._build_provider_keys(AIProviderKeyConfig.Kind.API, DEFAULT_API_KEYS, payload_key="api")
        search_keys = self._build_provider_keys(AIProviderKeyConfig.Kind.SEARCH, DEFAULT_SEARCH_KEYS, payload_key="search")
        tool_keys = self._build_provider_keys(AIProviderKeyConfig.Kind.TOOL, DEFAULT_TOOL_KEYS, payload_key="tool")
        models = self._build_models(model_rows=model_rows)
        user_info = self._build_user_info()
        trial = self._build_trial_state(request.user)
        trial_model_policy = self._build_trial_model_policy(
            provider_by_company=provider_by_company,
            model_company_by_name=model_company_by_name,
        )

        revision = self._resolve_revision()
        payload = {
            "revision": revision,
            "scenarios": scenarios,
            "api_keys": api_keys,
            "search_keys": search_keys,
            "tool_keys": tool_keys,
            "all_models": models,
            "user_info": user_info,
            "trial": trial,
            "trial_model_policy": trial_model_policy,
        }
        return success_response(payload, msg="ok", code=0)

    def _build_scenarios(self, provider_by_company, model_company_by_name):
        """Each scenario key maps to ``default_model`` + ``models[]`` (multi-model bindings)."""
        payload = {}
        for scenario_key in DEFAULT_SCENARIOS.keys():
            bindings = (
                AIScenarioModelBinding.objects.select_related("model")
                .filter(scenario=scenario_key, is_active=True)
                .order_by("position", "id")
            )
            fallback = DEFAULT_SCENARIOS.get(scenario_key) or {}
            if not bindings.exists():
                merged = self._merge_provider_for_model(
                    model_name=str(fallback.get("model", "") or ""),
                    fallback_endpoint=str(fallback.get("endpoint", "") or ""),
                    fallback_api_key=str(fallback.get("api_key", "") or ""),
                    provider_by_company=provider_by_company,
                    model_company_by_name=model_company_by_name,
                )
                model_name = str(fallback.get("model", "") or "")
                if not model_name:
                    payload[scenario_key] = {
                        "default_model": "",
                        "models": [],
                    }
                    continue
                payload[scenario_key] = {
                    "default_model": model_name,
                    "models": [
                        {
                            "model": model_name,
                            "is_default": True,
                            "identity": "model",
                            "temperature": float(fallback.get("temperature", 0.2)),
                            "max_tokens": int(fallback.get("max_tokens", 2048)),
                            "endpoint": merged["endpoint"],
                            "api_key": merged["api_key"],
                            "provider_company": merged["provider_company"],
                            "provider_name": merged["provider_name"],
                        }
                    ],
                }
                continue

            models_list = []
            default_model = None
            for row in bindings:
                merged = self._merge_provider_for_model(
                    model_name=row.model.name,
                    fallback_endpoint=str(fallback.get("endpoint", "") or ""),
                    fallback_api_key=str(fallback.get("api_key", "") or ""),
                    provider_by_company=provider_by_company,
                    model_company_by_name=model_company_by_name,
                )
                if row.is_default:
                    default_model = row.model.name
                models_list.append(
                    {
                        "model": row.model.name,
                        "is_default": bool(row.is_default),
                        "identity": row.identity,
                        "temperature": row.temperature,
                        "max_tokens": row.max_tokens,
                        "endpoint": merged["endpoint"],
                        "api_key": merged["api_key"],
                        "provider_company": merged["provider_company"],
                        "provider_name": merged["provider_name"],
                    }
                )
            if default_model is None and models_list:
                default_model = models_list[0]["model"]
                for item in models_list:
                    item["is_default"] = item["model"] == default_model
            payload[scenario_key] = {"default_model": default_model or "", "models": models_list}
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
                "privacy_policy_url": row.privacy_policy_url,
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

    def _build_models(self, model_rows=None):
        rows = model_rows if model_rows is not None else list(
            AIModelCatalog.objects.filter(is_active=True).order_by("position", "name")
        )
        if not rows:
            return DEFAULT_MODELS

        return [
            {
                "name": row.name,
                "display_name": row.display_name,
                "position": row.position,
                "company": row.company,
                "is_hidden": row.is_hidden,
                "supports_search": row.supports_search,
                "supports_multimodal": row.supports_multimodal,
                "supports_reasoning": row.supports_reasoning,
                "supports_tool_use": row.supports_tool_use,
                "supports_voice_gen": row.supports_voice_gen,
                "supports_image_gen": row.supports_image_gen,
                "price_tier": row.price_tier,
                "supports_text": row.supports_text,
                "reasoning_controllable": row.reasoning_controllable,
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

    def _build_trial_state(self, user):
        trial = TrialApplication.objects.filter(user=user).first()
        trial = TrialService.ensure_status_fresh(trial=trial)

        if trial is None:
            return {
                "status": TrialApplication.Status.NONE,
                "is_active": False,
                "grant_source": TrialApplication.GrantSource.AUTO,
                "started_at": None,
                "expires_at": None,
                "remaining_seconds": 0,
            }

        now = timezone.now()
        remaining_seconds = 0
        if trial.expires_at:
            remaining_seconds = max(int((trial.expires_at - now).total_seconds()), 0)
        return {
            "status": trial.status,
            "is_active": trial.is_active_trial(),
            "grant_source": trial.grant_source,
            "started_at": trial.started_at.isoformat() if trial.started_at else None,
            "expires_at": trial.expires_at.isoformat() if trial.expires_at else None,
            "remaining_seconds": remaining_seconds,
        }

    def _build_trial_model_policy(self, provider_by_company, model_company_by_name):
        policy = TrialModelPolicy.objects.filter(is_active=True).order_by("-updated_at").first()
        if policy is None:
            return []

        rows = (
            TrialModelPolicyItem.objects.select_related("model").filter(policy=policy, is_active=True).order_by("position", "scenario")
        )
        result = []
        for row in rows:
            fallback = DEFAULT_SCENARIOS.get(row.scenario) or {}
            merged = self._merge_provider_for_model(
                model_name=row.model.name,
                fallback_endpoint=str(fallback.get("endpoint", "") or ""),
                fallback_api_key=str(fallback.get("api_key", "") or ""),
                provider_by_company=provider_by_company,
                model_company_by_name=model_company_by_name,
            )
            result.append(
                {
                    "scenario": row.scenario,
                    "model": row.model.name,
                    "is_default": bool(row.is_default),
                    "identity": row.identity,
                    "endpoint": merged["endpoint"],
                    "api_key": merged["api_key"],
                    "temperature": row.temperature,
                    "max_tokens": row.max_tokens,
                    "provider_company": merged["provider_company"],
                    "provider_name": merged["provider_name"],
                }
            )
        return result

    def _build_provider_index(self, provider_rows):
        # 每个厂商只选一个“当前生效 provider”（优先 is_using，再按 position）。
        provider_by_company = {}
        for row in provider_rows:
            normalized_company = str(row.company or "").strip().upper()
            if not normalized_company:
                continue
            if normalized_company not in provider_by_company:
                provider_by_company[normalized_company] = row
        return provider_by_company

    def _merge_provider_for_model(
        self,
        model_name: str,
        fallback_endpoint: str,
        fallback_api_key: str,
        provider_by_company,
        model_company_by_name,
    ):
        company = str(model_company_by_name.get(model_name, "") or "").strip().upper()
        provider = provider_by_company.get(company)
        if provider is None:
            return {
                "endpoint": fallback_endpoint,
                "api_key": fallback_api_key or "",
                "provider_company": company or "",
                "provider_name": "",
            }
        return {
            "endpoint": provider.request_url or fallback_endpoint,
            "api_key": provider.key or fallback_api_key or "",
            "provider_company": provider.company,
            "provider_name": provider.name,
        }

    def _resolve_revision(self):
        points = [
            AIScenarioModelBinding.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
            AIProviderKeyConfig.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
            AIModelCatalog.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
            AIBootstrapProfile.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
            TrialApplication.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
            TrialModelPolicy.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
            TrialModelPolicyItem.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
        ]
        points = [point for point in points if point is not None]
        if not points:
            return timezone.now().isoformat()
        return max(points).isoformat()


class TrialStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        trial = TrialApplication.objects.filter(user=request.user).first()
        trial = TrialService.ensure_status_fresh(trial=trial)

        if trial is None:
            payload = {
                "status": TrialApplication.Status.NONE,
                "is_active": False,
                "grant_source": TrialApplication.GrantSource.AUTO,
                "started_at": None,
                "expires_at": None,
                "remaining_seconds": 0,
            }
            return success_response(payload, msg="ok", code=0)

        now = timezone.now()
        remaining_seconds = 0
        if trial.expires_at:
            remaining_seconds = max(int((trial.expires_at - now).total_seconds()), 0)
        payload = {
            "status": trial.status,
            "is_active": trial.is_active_trial(),
            "grant_source": trial.grant_source,
            "started_at": trial.started_at.isoformat() if trial.started_at else None,
            "expires_at": trial.expires_at.isoformat() if trial.expires_at else None,
            "remaining_seconds": remaining_seconds,
            "note": trial.note,
        }
        return success_response(payload, msg="ok", code=0)


class TrialApplyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        note = str(request.data.get("note", "") or "")
        trial = TrialService.apply_trial(user=request.user, note=note)
        trial = TrialService.ensure_status_fresh(trial=trial)

        now = timezone.now()
        remaining_seconds = 0
        if trial and trial.expires_at:
            remaining_seconds = max(int((trial.expires_at - now).total_seconds()), 0)

        payload = {
            "status": trial.status if trial else TrialApplication.Status.NONE,
            "is_active": bool(trial and trial.is_active_trial()),
            "grant_source": trial.grant_source if trial else TrialApplication.GrantSource.APPLICATION,
            "started_at": trial.started_at.isoformat() if trial and trial.started_at else None,
            "expires_at": trial.expires_at.isoformat() if trial and trial.expires_at else None,
            "remaining_seconds": remaining_seconds,
            "note": trial.note if trial else "",
        }
        return success_response(payload, msg="trial_updated", code=0, status_code=status.HTTP_200_OK)


class AIProviderConnectionTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_url = str(request.data.get("request_url", "") or "").strip()
        api_key = str(request.data.get("api_key", "") or "").strip()
        model = str(request.data.get("model", "") or "").strip() or "spark-chat-default"

        if not request_url:
            return success_response({"reachable": False, "message": "request_url_required"}, msg="ok", code=0)
        if not api_key:
            return success_response({"reachable": False, "message": "api_key_required"}, msg="ok", code=0)
        if request_url.startswith("http://") is False and request_url.startswith("https://") is False:
            return success_response({"reachable": False, "message": "invalid_request_url"}, msg="ok", code=0)

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 4,
            "temperature": 0,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            request_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        try:
            with urllib_request.urlopen(req, timeout=8) as response:
                ok = 200 <= int(response.status) < 300
                return success_response({"reachable": ok, "message": "ok" if ok else "http_error"}, msg="ok", code=0)
        except urllib_error.HTTPError as exc:
            return success_response({"reachable": False, "message": f"http_{exc.code}"}, msg="ok", code=0)
        except Exception:
            return success_response({"reachable": False, "message": "network_error"}, msg="ok", code=0)
