from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    "migrations",
    "总领文档",
    ".next",
    "dist",
    "build",
    "coverage",
    "tmp",
}
SKIP_FILE_NAMES = {
    "test_runtime_cleanup.py",
    "KNOWLEDGE-SIMPLIFY-000003-知识库收敛为客户端同步创建与读取需求工单.md",
}
ALLOWED_HITS = {
    ("ai_config/models.py", "search_knowledge_bag"),
}
SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".md"}
NEEDLES = (
    "KnowledgeChunk",
    "KnowledgeIndexState",
    "KnowledgeIndexVersion",
    "KnowledgeRetrievalAudit",
    "search_knowledge_bag",
    "KnowledgeEmbedding",
    "index_document_task",
    "rebuild_index_version_task",
    "extract_document_task",
    "KNOWLEDGE_RAG_TOOL_ENABLED",
    "KNOWLEDGE_CHAT_SELECTOR_ENABLED",
)


class KnowledgeRuntimeCleanupTests(SimpleTestCase):
    def test_removed_symbols_are_absent_from_runtime_code(self):
        hits: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.name in SKIP_FILE_NAMES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for needle in NEEDLES:
                if needle in text:
                    relative = str(path.relative_to(ROOT))
                    if (relative, needle) in ALLOWED_HITS:
                        continue
                    hits.append(f"{relative}:{needle}")
        self.assertEqual(hits, [], "removed knowledge symbols still appear in runtime files:\n" + "\n".join(hits))
