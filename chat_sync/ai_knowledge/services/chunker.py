from __future__ import annotations

import hashlib

from chat_sync.ai_knowledge.constants import CHUNK_CHAR_SIZE, CHUNK_OVERLAP, MAX_CHUNKS_PER_DOCUMENT


def chunk_text(content: str, *, size: int = CHUNK_CHAR_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    text = (content or "").strip()
    if not text:
        return []
    size = max(200, size)
    overlap = max(0, min(overlap, size // 4))
    chunks: list[dict] = []
    start = 0
    sequence = 0
    while start < len(text) and sequence < MAX_CHUNKS_PER_DOCUMENT:
        end = min(len(text), start + size)
        piece = text[start:end].strip()
        if piece:
            digest = hashlib.sha256(piece.encode("utf-8")).hexdigest()
            chunks.append(
                {
                    "sequence": sequence,
                    "content": piece,
                    "content_hash": digest,
                    "token_count": max(1, len(piece) // 2),
                }
            )
            sequence += 1
        if end >= len(text):
            break
        start = end - overlap
    return chunks
