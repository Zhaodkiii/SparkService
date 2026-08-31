from __future__ import annotations

from django.conf import settings

NAMED_BASE_QUOTA = int(getattr(settings, "KNOWLEDGE_NAMED_BASE_QUOTA", 20))
