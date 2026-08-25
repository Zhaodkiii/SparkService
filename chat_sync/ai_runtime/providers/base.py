from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from .types import ProviderChatRequest, ProviderChunk


class BaseProviderGateway(ABC):
    @abstractmethod
    async def stream(self, request: ProviderChatRequest) -> AsyncIterator[ProviderChunk]:
        raise NotImplementedError

