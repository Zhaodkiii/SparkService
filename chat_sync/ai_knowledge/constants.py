from __future__ import annotations

from django.conf import settings

KNOWLEDGE_FILE_BUSINESS_TYPE = "knowledge_base"
NAMED_BASE_QUOTA = int(getattr(settings, "KNOWLEDGE_NAMED_BASE_QUOTA", 20))
MAX_FILE_BYTES = int(getattr(settings, "KNOWLEDGE_MAX_FILE_BYTES", 20 * 1024 * 1024))
MAX_CHUNKS_PER_DOCUMENT = int(getattr(settings, "KNOWLEDGE_MAX_CHUNKS_PER_DOCUMENT", 200))
MAX_CHUNKS_PER_BASE = int(getattr(settings, "KNOWLEDGE_MAX_CHUNKS_PER_BASE", 4000))
CHUNK_CHAR_SIZE = int(getattr(settings, "KNOWLEDGE_CHUNK_CHAR_SIZE", 800))
CHUNK_OVERLAP = int(getattr(settings, "KNOWLEDGE_CHUNK_OVERLAP", 80))
CHUNKER_VERSION = "char.v1"
EXTRACTOR_VERSION = "extract.v1"
SUPPORTED_FILE_EXTS = {".txt", ".md", ".markdown", ".pdf", ".docx"}
SUPPORTED_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
