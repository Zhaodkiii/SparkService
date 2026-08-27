from __future__ import annotations

from pathlib import Path


class ExtractionError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def extract_text(*, file_name: str, mime_type: str, payload: bytes) -> str:
    ext = Path(file_name or "").suffix.lower()
    mime = (mime_type or "").lower()
    if ext in {".txt", ".md", ".markdown"} or mime in {"text/plain", "text/markdown"}:
        return payload.decode("utf-8", errors="replace")
    if ext == ".pdf" or mime == "application/pdf":
        return _extract_pdf(payload)
    if ext == ".docx" or mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx(payload)
    raise ExtractionError("knowledge_file_unsupported")


def _extract_pdf(payload: bytes) -> str:
    try:
        from io import BytesIO
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError("knowledge_file_unsupported", "pypdf is not installed") from exc
    reader = PdfReader(BytesIO(payload))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages).strip()
    if not text:
        raise ExtractionError("knowledge_file_unsupported", "empty pdf text")
    return text


def _extract_docx(payload: bytes) -> str:
    try:
        from io import BytesIO
        from docx import Document
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError("knowledge_file_unsupported", "python-docx is not installed") from exc
    document = Document(BytesIO(payload))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
    if not text:
        raise ExtractionError("knowledge_file_unsupported", "empty docx text")
    return text
