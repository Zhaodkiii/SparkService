from __future__ import annotations

from django.db.models import Max

from ai_config.models import AIModelCatalog, AIProviderKeyConfig, AIScenarioModelBinding, IdentityKind, ScenarioKey
from chat_sync.ai_runtime.providers.types import ProviderRoute

from hospital_care.exceptions import HospitalCareError


def catalog_model_by_name(name: str) -> AIModelCatalog:
    model = AIModelCatalog.objects.filter(name=name).first()
    if model is None:
        raise HospitalCareError("AGENT_BASE_MODEL_UNAVAILABLE", details={"field": "binding.model"})
    return model


def assert_catalog_model_available(model: AIModelCatalog, *, error_code: str = "AGENT_BASE_MODEL_UNAVAILABLE"):
    if not model.is_active:
        raise HospitalCareError(error_code, details={"field": "model", "reason": "inactive"})
    provider = (
        AIProviderKeyConfig.objects.filter(
            kind=AIProviderKeyConfig.Kind.API,
            company=model.company,
            is_active=True,
        )
        .exclude(key="")
        .exclude(request_url="")
        .order_by("-is_using", "position", "id")
        .first()
    )
    if provider is None:
        raise HospitalCareError(error_code, details={"field": "provider", "company": model.company})
    return provider


def next_agent_binding_position() -> int:
    last = (
        AIScenarioModelBinding.objects.filter(scenario=ScenarioKey.CHAT, identity=IdentityKind.AGENT).aggregate(value=Max("position"))
    )["value"]
    return int(last or 0) + 1


def resolve_embedding_route_for_binding(binding_id) -> tuple[AIScenarioModelBinding, ProviderRoute]:
    binding = (
        AIScenarioModelBinding.objects.select_related("model")
        .filter(
            pk=binding_id,
            scenario=ScenarioKey.EMBEDDING,
            is_active=True,
            model__is_active=True,
        )
        .first()
    )
    if binding is None:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_EMBEDDING_UNAVAILABLE", details={"field": "embedding_binding_id"})
    try:
        provider = assert_catalog_model_available(
            binding.model,
            error_code="HOSPITAL_KNOWLEDGE_EMBEDDING_UNAVAILABLE",
        )
    except HospitalCareError:
        raise
    if not provider.key or not provider.request_url:
        raise HospitalCareError("HOSPITAL_KNOWLEDGE_EMBEDDING_UNAVAILABLE", details={"field": "provider"})
    return binding, ProviderRoute(
        provider=provider.company,
        model=binding.model.name,
        endpoint=provider.request_url,
        api_key=provider.key,
        config_version=str(binding.updated_at.isoformat()),
    )


def embedding_bindings_for_form() -> list[AIScenarioModelBinding]:
    return list(
        AIScenarioModelBinding.objects.select_related("model")
        .filter(scenario=ScenarioKey.EMBEDDING, is_active=True, model__is_active=True)
        .order_by("-is_default", "position", "id")
    )


def chat_models_for_form() -> list[AIModelCatalog]:
    models = list(AIModelCatalog.objects.filter(is_active=True).order_by("position", "name"))
    available = []
    companies = {
        row.company
        for row in AIProviderKeyConfig.objects.filter(kind=AIProviderKeyConfig.Kind.API, is_active=True)
        .exclude(key="")
        .exclude(request_url="")
    }
    for model in models:
        if model.company in companies:
            available.append(model)
    return available
