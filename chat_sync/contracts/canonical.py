"""Canonical block contract (CHAT-DATA-026).

Single strict source of truth aligned to iOS ``ChatMessage.swift``.

* ``ChatMessageBlockNodeRole`` has exactly three cases — ``timeline``,
  ``tool`` and ``toolPresentation``.  Their wire values are the camelCase
  Swift ``String``-raw-value case names.
* ``ChatMessageBlockKind`` has 37 camelCase cases.  ``toolCall`` and
  ``toolResult`` are **not** values in that enum: a tool invocation is ``tool``
  and its result is a ``toolPresentation`` rich card.
* ``ChatMessageBlockPayload`` is a tagged union encoded as ``{"<kind>": {"_0":
  value}}``.  JSONEncoder's ``convertToSnakeCase`` strategy makes the payload
  discriminator snake_case, while the conceptual ``kind`` remains camelCase; the single
  associated value is always wrapped under ``_0`` (Swift's synthesized enum
  encoding).  iOS computes ``block.kind`` from ``payload.kind``; the wire never
  serialises a standalone ``kind`` field.
* ``ChatBlockAnchor`` is the iOS union ``{type, value?}`` where ``value`` only
  exists for ``beforeBlock``/``afterBlock``/``toolCall``.

The server **accepts, persists and projects only** canonical blocks.  There is
no legacy read / normalisation / migration path.  Non-canonical input is
rejected with :class:`BlockContractError`; it is never silently coerced to
``text`` or ``timeline``.
"""

from __future__ import annotations

import uuid
import re
from dataclasses import dataclass
from typing import Any

# --- NodeRole ---------------------------------------------------------------

NODE_ROLE_TIMELINE = "timeline"
NODE_ROLE_TOOL = "tool"
NODE_ROLE_TOOL_PRESENTATION = "toolPresentation"

NODE_ROLES = frozenset({NODE_ROLE_TIMELINE, NODE_ROLE_TOOL, NODE_ROLE_TOOL_PRESENTATION})

# --- BlockKind --------------------------------------------------------------

KIND_TEXT = "text"
KIND_DEEP_THOUGHT = "deepThought"
KIND_TOOL = "tool"
KIND_IMAGE_GALLERY = "imageGallery"
# DOCTOR-WORKSPACE-000004：医生问诊文档附件（PDF 等）画廊块。
KIND_FILE_GALLERY = "fileGallery"
KIND_FILE_ATTACHMENTS = "fileAttachments"
KIND_KNOWLEDGE_CARDS = "knowledgeCards"
KIND_TRANSLATED_TEXT = "translatedText"
KIND_MAP_ROUTE = "mapRoute"
KIND_EVENTS = "events"
KIND_HEALTH_CARDS = "healthCards"
KIND_PENDING_MEMBER_TOOL_CARDS = "pendingMemberToolCards"
KIND_TOOL_QUESTION_CARDS = "toolQuestionCards"
KIND_TOOL_MEMBER_SELECTION_CARDS = "toolMemberSelectionCards"
KIND_HEALTH_RESOURCE_CANDIDATE_CARDS = "healthResourceCandidateCards"
KIND_TOOL_CONSENT_CARDS = "toolConsentCards"
KIND_LOCATION_PERMISSION_CARDS = "locationPermissionCards"
KIND_STRUCTURED_HEALTH_CARDS = "structuredHealthCards"
KIND_SLEEP_VISUALIZATION = "sleepVisualization"
KIND_STEP_VISUALIZATION = "stepVisualization"
KIND_ENERGY_VISUALIZATION = "energyVisualization"
KIND_NUTRITION_READ_VISUALIZATION = "nutritionReadVisualization"
KIND_WEATHER_VISUALIZATION = "weatherVisualization"
KIND_WEATHER_CONFIG_CARD = "weatherConfigCard"
KIND_SEARCH_SUMMARY = "searchSummary"
KIND_NUTRITION_CARDS = "nutritionCards"
KIND_WORKOUT_VISUALIZATION = "workoutVisualization"
KIND_CAPTURE_CARD = "captureCard"
KIND_HTML = "html"
KIND_SMALL_TASK_CARD = "smallTaskCard"
KIND_TASK_CARDS = "taskCards"
KIND_ERROR = "error"
KIND_ASSISTANT_STATUS_CARD = "assistantStatusCard"
KIND_HEALTH_RESOURCE_REFERENCE = "healthResourceReference"
KIND_MEDICAL_RISK_NOTICE = "medicalRiskNotice"
KIND_MEDICAL_DISCLAIMER_CARD = "medicalDisclaimerCard"
KIND_CHAT_GUIDE_CARD = "chatGuideCard"
KIND_HOSPITAL_DOCTOR_INTRO_CARD = "hospitalDoctorIntroCard"

BLOCK_KINDS = frozenset({
    KIND_TEXT,
    KIND_DEEP_THOUGHT,
    KIND_TOOL,
    KIND_IMAGE_GALLERY,
    KIND_FILE_GALLERY,
    KIND_FILE_ATTACHMENTS,
    KIND_KNOWLEDGE_CARDS,
    KIND_TRANSLATED_TEXT,
    KIND_MAP_ROUTE,
    KIND_EVENTS,
    KIND_HEALTH_CARDS,
    KIND_PENDING_MEMBER_TOOL_CARDS,
    KIND_TOOL_QUESTION_CARDS,
    KIND_TOOL_MEMBER_SELECTION_CARDS,
    KIND_HEALTH_RESOURCE_CANDIDATE_CARDS,
    KIND_TOOL_CONSENT_CARDS,
    KIND_LOCATION_PERMISSION_CARDS,
    KIND_STRUCTURED_HEALTH_CARDS,
    KIND_SLEEP_VISUALIZATION,
    KIND_STEP_VISUALIZATION,
    KIND_ENERGY_VISUALIZATION,
    KIND_NUTRITION_READ_VISUALIZATION,
    KIND_WEATHER_VISUALIZATION,
    KIND_WEATHER_CONFIG_CARD,
    KIND_SEARCH_SUMMARY,
    KIND_NUTRITION_CARDS,
    KIND_WORKOUT_VISUALIZATION,
    KIND_CAPTURE_CARD,
    KIND_HTML,
    KIND_SMALL_TASK_CARD,
    KIND_TASK_CARDS,
    KIND_ERROR,
    KIND_ASSISTANT_STATUS_CARD,
    KIND_HEALTH_RESOURCE_REFERENCE,
    KIND_MEDICAL_RISK_NOTICE,
    KIND_MEDICAL_DISCLAIMER_CARD,
    KIND_CHAT_GUIDE_CARD,
    KIND_HOSPITAL_DOCTOR_INTRO_CARD,
})


def _swift_json_key(case_name: str) -> str:
    """Match JSONEncoder.KeyEncodingStrategy.convertToSnakeCase used by iOS."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", case_name).lower()


KIND_TO_PAYLOAD_KEY = {kind: _swift_json_key(kind) for kind in BLOCK_KINDS}
PAYLOAD_KEY_TO_KIND = {key: kind for kind, key in KIND_TO_PAYLOAD_KEY.items()}
PAYLOAD_KEYS = frozenset(PAYLOAD_KEY_TO_KIND)

# --- Anchor -----------------------------------------------------------------

ANCHOR_TYPE_MESSAGE_START = "messageStart"
ANCHOR_TYPE_MESSAGE_END = "messageEnd"
ANCHOR_TYPE_BEFORE_BLOCK = "beforeBlock"
ANCHOR_TYPE_AFTER_BLOCK = "afterBlock"
ANCHOR_TYPE_TOOL_CALL = "toolCall"

ANCHOR_TYPES = frozenset({
    ANCHOR_TYPE_MESSAGE_START,
    ANCHOR_TYPE_MESSAGE_END,
    ANCHOR_TYPE_BEFORE_BLOCK,
    ANCHOR_TYPE_AFTER_BLOCK,
    ANCHOR_TYPE_TOOL_CALL,
})

# These anchor cases carry a ``value``.
ANCHOR_TYPES_WITH_VALUE = frozenset({
    ANCHOR_TYPE_BEFORE_BLOCK,
    ANCHOR_TYPE_AFTER_BLOCK,
    ANCHOR_TYPE_TOOL_CALL,
})


class BlockContractError(Exception):
    """A canonical block failed strict validation (CHAT-DATA-026 §11)."""

    def __init__(self, code: str, message: str, block_index: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.block_index = block_index


@dataclass(frozen=True)
class DecodedPayload:
    kind: str
    value: Any


@dataclass(frozen=True)
class CanonicalBlock:
    kind: str
    node_role: str
    anchor: Any
    payload: dict[str, Any]


# --- Payload union builders -------------------------------------------------

def _wrap(value: Any) -> dict[str, Any]:
    return {"_0": value}


def text_payload(text: str) -> dict[str, Any]:
    return {KIND_TO_PAYLOAD_KEY[KIND_TEXT]: _wrap(text)}


def error_payload(message: str) -> dict[str, Any]:
    return {KIND_TO_PAYLOAD_KEY[KIND_ERROR]: _wrap(message)}


def tool_payload(
    name: str | None,
    content: str,
    invocation_arguments: dict[str, str] | None = None,
) -> dict[str, Any]:
    inner: dict[str, Any] = {"name": name, "content": content}
    if invocation_arguments:
        inner["invocation_arguments"] = invocation_arguments
    return {KIND_TO_PAYLOAD_KEY[KIND_TOOL]: _wrap(inner)}


def deep_thought_payload(
    reasoning_content: str | None,
    reasoning_duration_ms: int | None,
    reasoning_expanded: bool,
    reasoning_visibility: str,
) -> dict[str, Any]:
    return {
        KIND_TO_PAYLOAD_KEY[KIND_DEEP_THOUGHT]: _wrap({
            "reasoning_content": reasoning_content,
            "reasoning_duration_ms": reasoning_duration_ms,
            "reasoning_expanded": reasoning_expanded,
            "reasoning_visibility": reasoning_visibility,
        })
    }


def search_summary_payload(
    provider_name: str,
    query: str,
    keywords: list[str] | None = None,
    references: list[dict[str, Any]] | None = None,
    total_estimated_matches: int | None = None,
) -> dict[str, Any]:
    return {
        KIND_TO_PAYLOAD_KEY[KIND_SEARCH_SUMMARY]: _wrap({
            "id": str(uuid.uuid4()),
            "provider_name": provider_name,
            "query": query,
            "keywords": keywords or [],
            "references": references or [],
            "total_estimated_matches": total_estimated_matches,
        })
    }


def hospital_doctor_intro_card_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {KIND_TO_PAYLOAD_KEY[KIND_HOSPITAL_DOCTOR_INTRO_CARD]: _wrap(snapshot)}


def assistant_status_payload(status_type: str, message: str) -> dict[str, Any]:
    return {
        KIND_TO_PAYLOAD_KEY[KIND_ASSISTANT_STATUS_CARD]: _wrap({
            "type": status_type,
            "message": message,
        })
    }


def tool_question_cards_payload(
    *,
    run_id: str,
    interaction_id: str,
    interaction_key: str,
    tool_call_id: str,
    tool_name: str,
    tool_version: str,
    schema_version: int,
    status: str,
    question_ids: list[str],
    request: dict[str, Any],
    expires_at: str | None,
    answers: list[dict[str, Any]] | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Canonical ask_user interaction card. Never carries raw tool arguments."""
    inner: dict[str, Any] = {
        "run_id": run_id,
        "interaction_id": interaction_id,
        "interaction_key": interaction_key,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "tool_version": tool_version,
        "schema_version": schema_version,
        "status": status,
        "question_ids": question_ids,
        "request": request if isinstance(request, dict) else {},
        "expires_at": expires_at,
    }
    if answers is not None:
        inner["answers"] = answers
    if error_code:
        inner["error_code"] = error_code
    return {KIND_TO_PAYLOAD_KEY[KIND_TOOL_QUESTION_CARDS]: _wrap(inner)}


# --- Tool result → presentation card registry --------------------------------
#
# Tool results are projected to one of the 36 iOS presentation kinds (never a
# standalone ``toolCall``/``toolResult`` and never an empty ``text``).  The P4
# server tools are all read/reference tools that return a *list of sources*, so
# Their canonical result card is ``searchSummary`` whose ``references`` carries
# the projected ``source_refs``.  Tools that return a single resource identity
# or a rich domain card would register their own kind here (e.g.
# ``healthResourceReference`` / ``knowledgeCards``); those payloads require data
# the P4 read tools do not produce.

TOOL_PRESENTATION_KIND: dict[str, str] = {}

DEFAULT_TOOL_PRESENTATION_KIND = KIND_SEARCH_SUMMARY


def tool_presentation_kind(tool_name: str) -> str:
    return TOOL_PRESENTATION_KIND.get(tool_name, DEFAULT_TOOL_PRESENTATION_KIND)


def tool_result_presentation_payload(
    tool_name: str,
    display_name: str,
    result_preview: str | None,
    source_refs: list[dict[str, Any]] | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Project a tool result to its canonical toolPresentation card payload."""
    kind = tool_presentation_kind(tool_name)
    if kind == KIND_SEARCH_SUMMARY:
        references = []
        for ref in (source_refs or [])[:32]:
            if not isinstance(ref, dict):
                continue
            references.append({
                "id": str(uuid.uuid4()),
                "title": str(ref.get("title") or ref.get("source_id") or "source"),
                "url": str(ref.get("url") or ""),
                "snippet": ref.get("snippet"),
                "source_name": ref.get("type") or ref.get("source_name") or ref.get("sourceName"),
                "published_at": ref.get("published_at") or ref.get("publishedAt"),
            })
        return search_summary_payload(
            provider_name=display_name or tool_name,
            query=(query or result_preview or "").strip() or display_name or tool_name,
            keywords=[],
            references=references,
        )
    return search_summary_payload(
        provider_name=display_name or tool_name,
        query=(query or result_preview or "").strip() or display_name or tool_name,
        keywords=[],
        references=[],
    )


# --- Strict decode / validate ------------------------------------------------

def payload_kind(payload: Any) -> str | None:
    """Return the single discriminator kind of a canonical payload, else None.

    Non-raising helper: used for outbound diagnostics and text extraction.  A
    payload is canonical only when it is a dict with exactly one known kind key
    whose value is the Swift ``{"_0": ...}`` wrapper.
    """
    if not isinstance(payload, dict):
        return None
    candidates = [key for key in payload if key in PAYLOAD_KEYS]
    if len(candidates) != 1:
        return None
    wrapper = payload[candidates[0]]
    if not isinstance(wrapper, dict) or "_0" not in wrapper:
        return None
    return PAYLOAD_KEY_TO_KIND[candidates[0]]


def project_block_for_ios_client(kind: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Map hospital ``fileGallery`` onto iOS ``fileAttachments``.

    Doctor console stores PDF 病历 as ``fileGallery`` / ``type=document``.  iOS
    ``ChatMessageBlockPayload`` only has ``fileAttachments([ChatAttachment])``
    and ``ChatAttachmentType`` has ``pdf``/``file``, not ``document``.  Leaving
    the hospital shape on the chat-sync wire makes the whole pull fail with
    ``Invalid number of keys found, expected one``.
    """
    if kind != KIND_FILE_GALLERY:
        return kind, payload
    wrapper: Any = {}
    if isinstance(payload, dict):
        wrapper = payload.get("file_gallery") or payload.get("fileGallery") or {}
    raw_items = wrapper.get("_0") if isinstance(wrapper, dict) else None
    items: list[dict[str, Any]] = []
    if isinstance(raw_items, list):
        items = [_project_ios_attachment(item) for item in raw_items if isinstance(item, dict)]
    return KIND_FILE_ATTACHMENTS, {KIND_TO_PAYLOAD_KEY[KIND_FILE_ATTACHMENTS]: {"_0": items}}


def _project_ios_attachment(item: dict[str, Any]) -> dict[str, Any]:
    projected = dict(item)
    raw_type = str(projected.get("type") or "").strip().lower()
    mime = str(projected.get("mime_type") or projected.get("mimeType") or "").strip().lower()
    if raw_type in {"document", "application/pdf"} or mime == "application/pdf":
        projected["type"] = "pdf"
    elif raw_type not in {"image", "video", "pdf", "file"} and raw_type:
        projected["type"] = "file"
    return projected


def decode_payload(payload: Any) -> DecodedPayload:
    """Strictly decode a canonical payload union to ``(kind, associated_value)``.

    Raises :class:`BlockContractError` for any non-canonical shape; never
    defaults to ``text``.
    """
    if not isinstance(payload, dict) or not payload:
        raise BlockContractError("chat_block_payload_invalid", "payload 不是对象或为空")
    candidates = [key for key in payload if key in PAYLOAD_KEYS]
    if not candidates:
        raise BlockContractError("chat_block_payload_invalid", "payload 缺少已知 discriminator")
    if len(candidates) > 1:
        raise BlockContractError("chat_block_payload_ambiguous", "payload 包含多个 discriminator")
    payload_key = candidates[0]
    kind = PAYLOAD_KEY_TO_KIND[payload_key]
    wrapper = payload[payload_key]
    if not isinstance(wrapper, dict) or "_0" not in wrapper:
        raise BlockContractError("chat_block_payload_invalid", "payload discriminator 缺少 _0")
    return DecodedPayload(kind=kind, value=wrapper["_0"])


def validate_node_role(node_role: Any) -> str:
    """Return the canonical node_role or raise; unknown roles are not defaulted."""
    text = str(node_role or "")
    if text not in NODE_ROLES:
        raise BlockContractError("chat_block_node_role_invalid", f"未知 node_role: {text!r}")
    return text


def validate_kind_node_role(kind: str, node_role: str) -> None:
    """Reject combinations that never occur in the iOS model."""
    if kind == KIND_TOOL and node_role != NODE_ROLE_TOOL:
        raise BlockContractError(
            "chat_block_node_role_invalid",
            "tool 块必须使用 node_role=tool",
        )
    if kind == KIND_DEEP_THOUGHT and node_role != NODE_ROLE_TIMELINE:
        raise BlockContractError(
            "chat_block_node_role_invalid",
            "deepThought 块必须使用 node_role=timeline",
        )


def validate_anchor(anchor: Any) -> None:
    """Reject anchors that do not belong to the iOS ``ChatBlockAnchor`` union."""
    if anchor is None:
        return
    if not isinstance(anchor, dict) or "type" not in anchor:
        raise BlockContractError("chat_block_anchor_invalid", "anchor 缺少 type")
    anchor_type = anchor.get("type")
    if anchor_type not in ANCHOR_TYPES:
        raise BlockContractError("chat_block_anchor_invalid", f"未知 anchor type: {anchor_type!r}")
    if anchor_type in ANCHOR_TYPES_WITH_VALUE:
        value = anchor.get("value")
        if not isinstance(value, str) or not value:
            raise BlockContractError("chat_block_anchor_invalid", "anchor 需要非空 value")


def decode_block(block: dict[str, Any], *, block_index: int | None = None) -> CanonicalBlock:
    """Validate a raw wire block dict and return its canonical triple.

    - ``kind`` (if present) must equal the payload discriminator.
    - ``node_role`` is mandatory and must be one of the three iOS roles.
    - ``anchor`` must be a valid iOS anchor (or absent).
    """
    try:
        decoded = decode_payload(block.get("payload") or {})
    except BlockContractError as exc:
        exc.block_index = block_index
        raise

    explicit_kind = block.get("kind")
    if explicit_kind is not None and str(explicit_kind) not in ("", "None") and str(explicit_kind) != decoded.kind:
        raise BlockContractError(
            "chat_block_kind_mismatch",
            f"kind={explicit_kind!r} 与 payload discriminator {decoded.kind!r} 不一致",
            block_index=block_index,
        )

    node_role = block.get("node_role", block.get("nodeRole"))
    if node_role is None or str(node_role).strip() == "":
        raise BlockContractError("chat_block_node_role_invalid", "node_role 缺失", block_index=block_index)
    try:
        node_role = validate_node_role(node_role)
        validate_kind_node_role(decoded.kind, node_role)
        validate_anchor(block.get("anchor"))
    except BlockContractError as exc:
        exc.block_index = block_index
        raise

    return CanonicalBlock(
        kind=decoded.kind,
        node_role=node_role,
        anchor=block.get("anchor"),
        payload=block.get("payload") or {},
    )


def payload_text(payload: Any) -> str:
    """Return the plain text of a canonical ``text`` payload; empty otherwise."""
    kind = payload_kind(payload)
    if kind != KIND_TEXT:
        return ""
    return str(payload[KIND_TEXT].get("_0") or "")
