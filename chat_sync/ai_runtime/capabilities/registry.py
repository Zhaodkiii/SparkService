from __future__ import annotations

from collections.abc import Iterable

from .manifests.chat import manifest as chat_manifest
from .protocol import CapabilityManifest, CapabilityUnavailable


class CapabilityRegistry:
    def __init__(self, manifests: Iterable[CapabilityManifest] = ()) -> None:
        self._manifests: dict[tuple[str, str], CapabilityManifest] = {}
        for manifest in manifests:
            self.register(manifest)

    def register(self, manifest: CapabilityManifest) -> None:
        manifest.validate()
        key = (manifest.id, manifest.version)
        if key in self._manifests:
            raise ValueError(f"duplicate capability: {manifest.key}")
        self._manifests[key] = manifest

    def get(self, capability_id: str, version: str | None = None) -> CapabilityManifest | None:
        if version:
            return self._manifests.get((str(capability_id), str(version)))
        versions = [item for (item_id, _), item in self._manifests.items() if item_id == str(capability_id)]
        return sorted(versions, key=lambda item: item.version)[-1] if versions else None

    def require(self, capability_id: str, version: str | None = None) -> CapabilityManifest:
        manifest = self.get(capability_id, version)
        if manifest is None:
            raise CapabilityUnavailable(str(capability_id), "not_registered")
        if not manifest.enabled:
            raise CapabilityUnavailable(manifest.key, manifest.availability_reason or "disabled")
        return manifest

    def list(self, *, include_unavailable: bool = False) -> list[CapabilityManifest]:
        values = sorted(self._manifests.values(), key=lambda item: (item.id, item.version))
        return values if include_unavailable else [item for item in values if item.enabled]


def build_capability_registry() -> CapabilityRegistry:
    # Deep capabilities are registered only after their real providers and
    # artifact contracts exist. This makes availability truthful by default.
    return CapabilityRegistry([chat_manifest])


__all__ = ["CapabilityRegistry", "build_capability_registry"]
