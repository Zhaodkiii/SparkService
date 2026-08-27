from __future__ import annotations

import math
from typing import Any

import httpx
from django.conf import settings

from ai_config.models import AIProviderKeyConfig, AIScenarioModelBinding, ScenarioKey
from chat_sync.ai_runtime.providers.exceptions import LLMAPIError, LLMAuthenticationError, LLMConfigError, LLMTimeoutError
from chat_sync.ai_runtime.providers.types import ProviderRoute


def resolve_embedding_route() -> ProviderRoute:
    binding = (
        AIScenarioModelBinding.objects.select_related("model")
        .filter(scenario=ScenarioKey.EMBEDDING, is_active=True, model__is_active=True)
        .order_by("-is_default", "position", "id")
        .first()
    )
    if binding is None:
        raise LLMConfigError("no active embedding model binding")
    provider = (
        AIProviderKeyConfig.objects.filter(kind=AIProviderKeyConfig.Kind.API, company=binding.model.company, is_active=True)
        .order_by("-is_using", "position", "id")
        .first()
    )
    if provider is None or not provider.key or not provider.request_url:
        raise LLMConfigError("no active embedding provider credential")
    return ProviderRoute(
        provider=provider.company,
        model=binding.model.name,
        endpoint=provider.request_url,
        api_key=provider.key,
        config_version=str(binding.updated_at.isoformat()),
    )


class EmbeddingGateway:
    def __init__(self, route: ProviderRoute, *, timeout: float = 30, transport: httpx.BaseTransport | None = None):
        self.route = route
        self.timeout = timeout
        self.transport = transport

    @property
    def endpoint(self) -> str:
        value = self.route.endpoint.rstrip("/")
        if value.endswith("/embeddings"):
            return value
        if value.endswith("/chat/completions"):
            return value[: -len("/chat/completions")] + "/embeddings"
        return f"{value}/embeddings"

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        timeout = httpx.Timeout(self.timeout)
        headers = {"Authorization": f"Bearer {self.route.api_key}", "Content-Type": "application/json"}
        body = {"model": self.route.model, "input": texts}
        try:
            with httpx.Client(timeout=timeout, transport=self.transport) as client:
                response = client.post(self.endpoint, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(provider=self.route.provider) from exc
        except httpx.HTTPError as exc:
            raise LLMAPIError("embedding connection failed", provider=self.route.provider) from exc
        if response.status_code == 401:
            raise LLMAuthenticationError(provider=self.route.provider)
        if response.status_code >= 400:
            raise LLMAPIError("embedding provider returned an error", status_code=response.status_code, provider=self.route.provider)
        payload = response.json()
        items = payload.get("data") or []
        vectors: list[list[float]] = []
        for item in sorted(items, key=lambda row: int(row.get("index") or 0)):
            embedding = item.get("embedding") or []
            vectors.append([float(value) for value in embedding])
        if len(vectors) != len(texts):
            raise LLMAPIError("embedding count mismatch", provider=self.route.provider)
        return vectors


def vector_norm(values: list[float]) -> float:
    return math.sqrt(sum(value * value for value in values)) or 1.0


def cosine_similarity(left: list[float], right: list[float], left_norm: float | None = None, right_norm: float | None = None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    denom = (left_norm or vector_norm(left)) * (right_norm or vector_norm(right))
    if denom == 0:
        return 0.0
    return dot / denom
