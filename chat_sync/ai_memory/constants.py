from __future__ import annotations

L2_DOCUMENT_KEYS = frozenset({"chat", "knowledge", "medical", "nutrition"})
L3_DOCUMENT_KEYS = frozenset({"recent", "profile", "scope", "preferences"})
ALLOWED_SECTION_KEYS = frozenset(
    {
        "general",
        "answer_style",
        "language",
        "address",
        "format",
        "goals",
        "changes",
        "timeline",
        "background",
        "health_preferences",
        "identity",
        "knowledge",
        "capability",
        "facts",
        "notes",
    }
)
PREFERENCE_SECTION_KEYS = frozenset({"general", "answer_style", "language", "address", "format"})
MAX_CONTENT_CHARS = 240
MAX_TITLE_LENGTH = 128
MAX_RECALL_COUNT = 20
DEFAULT_RECALL_COUNT = 5
DEFAULT_READ_TOKEN_BUDGET = 1600
HARD_READ_TOKEN_BUDGET = 2000
MAX_MUTATIONS_PER_BATCH = 50
PULL_DEFAULT_LIMIT = 100
PULL_MAX_LIMIT = 200
RECEIPT_TTL_DAYS = 60
AGENT_SCOPE_ENABLED = False
THREAD_SCOPE_SYNC_ENABLED = False
