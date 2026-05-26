"""JSON-backed old_id -> new_id mapping for cross-batch migration."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from django.conf import settings


def id_map_path() -> Path:
    return Path(settings.BASE_DIR) / "scripts" / "migration" / "state" / "id_map.json"


class IdMap:
    _lock = threading.Lock()

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or id_map_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict[str, int]] = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        else:
            raw = {}
        self._data = {k: {str(oid): nid for oid, nid in v.items()} for k, v in raw.items()}

    def save(self) -> None:
        with self._lock:
            with self.path.open("w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, indent=2, sort_keys=True)

    def get(self, entity_type: str, old_id: Any) -> int | str | None:
        return self._data.get(entity_type, {}).get(str(old_id))

    def set(self, entity_type: str, old_id: Any, new_id: int | str) -> None:
        bucket = self._data.setdefault(entity_type, {})
        bucket[str(old_id)] = new_id

    def has(self, entity_type: str, old_id: Any) -> bool:
        return str(old_id) in self._data.get(entity_type, {})

    def pop(self, entity_type: str, old_id: Any) -> int | str | None:
        bucket = self._data.get(entity_type, {})
        return bucket.pop(str(old_id), None)

    def require(self, entity_type: str, old_id: Any) -> int | str | None:
        return self.get(entity_type, old_id)

    def stats(self) -> dict[str, int]:
        return {entity: len(ids) for entity, ids in self._data.items()}
