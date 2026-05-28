"""Field/value transforms for ZhaodkDream -> SparkService migration."""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone as dt_timezone
from typing import Any

from django.utils import timezone


def client_extra_dict(**fields: Any) -> dict[str, str]:
    """Build JSON extra compatible with iOS client `[String: String]`."""
    out: dict[str, str] = {}
    for key, value in fields.items():
        if value is None or value == "":
            continue
        if isinstance(value, (dict, list)):
            out[str(key)] = json.dumps(json_safe_value(value), ensure_ascii=False)
        else:
            out[str(key)] = str(value)
    return out


def migration_extra(legacy_table: str, legacy_id: Any, **extra: Any) -> dict[str, str]:
    fields: dict[str, Any] = {
        "migration_legacy_table": legacy_table,
        "migration_legacy_id": legacy_id,
    }
    for key, value in extra.items():
        fields[f"migration_{key}"] = value
    return client_extra_dict(**fields)


def normalize_country_code(value: Any) -> str:
    """Normalize to uppercase country/region code (e.g. CN/US)."""
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    # Legacy may store locale like "zh_CN" or "zh-CN".
    if "_" in text:
        text = text.split("_")[-1]
    if "-" in text:
        text = text.split("-")[-1]
    return text.upper()


def infer_country_code(*, language_code: Any = None, region_code: Any = None, time_zone: Any = None) -> str:
    """
    Infer most likely country code from legacy device signals.

    If cannot be inferred, default to CN (per migration requirement).
    """
    region = normalize_country_code(region_code)
    if region:
        return region

    lang = str(language_code or "").strip()
    if lang:
        # BCP47 examples: zh-Hans-CN / en-US / zh_CN
        candidate = normalize_country_code(lang)
        if candidate and len(candidate) in {2, 3}:
            return candidate
        lower = lang.lower()
        if lower.startswith("zh"):
            return "CN"

    tz = str(time_zone or "").strip()
    if tz:
        if tz.startswith("Asia/Shanghai") or tz.startswith("Asia/Chongqing") or tz.startswith("Asia/Harbin") or tz.startswith("Asia/Urumqi"):
            return "CN"
        if tz.startswith("Asia/Hong_Kong"):
            return "HK"
        if tz.startswith("Asia/Taipei"):
            return "TW"
        if tz.startswith("Asia/Macau"):
            return "MO"
        if tz.startswith("Asia/Tokyo"):
            return "JP"
        if tz.startswith("Asia/Seoul"):
            return "KR"
        if tz.startswith("America/"):
            return "US"

    return "CN"


def extra_needs_client_repair(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    if isinstance(value.get("migration"), dict):
        return True
    return any(isinstance(v, (dict, list)) for v in value.values())


def normalize_client_extra(value: Any) -> dict[str, str]:
    """Flatten nested migration metadata to `[String: String]` for the mobile client."""
    if not value:
        return {}
    if isinstance(value, str):
        parsed = parse_json_value(value, default=None)
        if isinstance(parsed, dict):
            value = parsed
        else:
            return {"legacy_text": value}
    if not isinstance(value, dict):
        return {}

    result: dict[str, str] = {}
    migration = value.get("migration")
    if isinstance(migration, dict):
        table = migration.get("legacy_table")
        legacy_id = migration.get("legacy_id")
        if table is not None:
            result["migration_legacy_table"] = str(table)
        if legacy_id is not None:
            result["migration_legacy_id"] = str(legacy_id)
        for key, val in migration.items():
            if key in {"legacy_table", "legacy_id"}:
                continue
            if val is None or val == "":
                continue
            out_key = f"migration_{key}"
            if isinstance(val, (dict, list)):
                result[out_key] = json.dumps(json_safe_value(val), ensure_ascii=False)
            else:
                result[out_key] = str(val)

    for key, val in value.items():
        if key == "migration":
            continue
        if val is None or val == "":
            continue
        if isinstance(val, (dict, list)):
            result[str(key)] = json.dumps(json_safe_value(val), ensure_ascii=False)
        else:
            result[str(key)] = str(val)
    return result


def truncate_char(value: Any, max_length: int) -> str:
    """Fit legacy text into a Django CharField without raising DataError."""
    if value is None:
        return ""
    text = str(value)
    if max_length <= 0:
        return ""
    return text[:max_length]


def char_field_with_overflow(
    value: Any,
    *,
    max_length: int,
    overflow_key: str,
) -> tuple[str, dict[str, str]]:
    """Truncate to CharField limit; keep full text in client-safe extra when clipped."""
    text = "" if value is None else str(value)
    if len(text) <= max_length:
        return text, {}
    return text[:max_length], {overflow_key: text}


def parse_json_value(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return json_safe_value(value)
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return json_safe_value(json.loads(text))
        except json.JSONDecodeError:
            return default
    return default


def json_safe_value(value: Any) -> Any:
    """Recursively convert values to JSON-serializable forms."""
    if isinstance(value, dict):
        return {str(k): json_safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_value(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return value


def aware_datetime(value: Any) -> Any:
    """Make naive legacy datetimes timezone-aware (UTC) for Django USE_TZ."""
    if value is None or not isinstance(value, datetime):
        return value
    if timezone.is_aware(value):
        return value
    return timezone.make_aware(value, timezone=dt_timezone.utc)


def gender_to_member(gender: str | None) -> str:
    mapping = {"男": "male", "女": "female", "male": "male", "female": "female"}
    return mapping.get((gender or "").strip(), "unknown")


def relationship_to_binding(relationship: str | None) -> str:
    text = (relationship or "").strip()
    mapping = {
        "本人": "self",
        "自己": "self",
        "父亲": "father",
        "母亲": "mother",
        "儿子": "child",
        "女儿": "child",
        "子女": "child",
        "配偶": "spouse",
        "丈夫": "spouse",
        "妻子": "spouse",
    }
    return mapping.get(text, text.lower() if text.isascii() else text)


def is_primary_relationship(relationship: str | None) -> bool:
    text = (relationship or "").strip()
    return text in {"本人", "自己", "self"}


def visit_type_to_new(value: str | None) -> str:
    mapping = {
        "门诊": "outpatient",
        "急诊": "emergency",
        "住院": "inpatient",
        "体检": "health_check",
    }
    return mapping.get((value or "").strip(), "custom")


def login_provider_to_new(provider: str | None) -> str | None:
    mapping = {
        "password": "password",
        "google": "google",
        "apple": "apple",
        "otp": "phone_otp",
        "email": "email_otp",
    }
    return mapping.get((provider or "").strip())


def login_outcome(success: Any) -> str:
    return "success" if bool(success) else "failed"


def deactivation_state(old_status: str | None) -> str:
    mapping = {
        "pending": "requested",
        "processing": "scheduled",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
    }
    return mapping.get((old_status or "").strip(), "requested")


def deactivation_audit_action(old_action: str | None) -> str:
    mapping = {
        "requested": "requested",
        "verified": "requested",
        "data_backup": "data_backup",
        "data_anonymize": "data_anonymize",
        "related_data_delete": "related_data_delete",
        "account_deactivate": "account_deactivate",
        "completed": "completed",
        "cancelled": "cancelled",
        "failed": "failed",
    }
    return mapping.get((old_action or "").strip(), "requested")


def trial_status_to_new(old_status: str | None) -> str:
    mapping = {
        "pending": "pending",
        "approved": "active",
        "rejected": "rejected",
        "expired": "expired",
        "revoked": "rejected",
    }
    return mapping.get((old_status or "").strip(), "none")


def normalize_migrated_trial(
    *,
    old_status: str | None,
    status: str,
    started_at,
    expires_at,
    applied_at=None,
):
    """Renew legacy approved trials whose expires_at is already in the past.

    Old ZhaodkDream trials were short-lived; SparkClient Pro bootstrap requires
  is_pro=true at login so the client can fetch /ai/config/bootstrap/.
    """
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone as tz

    now = tz.now()
    started_at = aware_datetime(started_at)
    expires_at = aware_datetime(expires_at)
    applied_at = aware_datetime(applied_at)
    legacy_status = (old_status or "").strip()

    if status != "active":
        return status, started_at, expires_at, applied_at, False

    if legacy_status not in {"approved", "active"}:
        return status, started_at, expires_at, applied_at, False

    renewed = False
    if expires_at is None or expires_at <= now:
        days = int(getattr(settings, "AI_TRIAL_DURATION_DAYS", 15))
        expires_at = now + timedelta(days=days)
        renewed = True
    if started_at is None or renewed:
        started_at = applied_at or now
        renewed = True
    return status, started_at, expires_at, applied_at or started_at, renewed


def usage_kind_to_scenario(usage_kind: str | None) -> str:
    mapping = {
        "chat": "chat",
        "embedding": "embedding",
        "voice": "voice",
        "optimization_text": "optimization_text",
        "optimization_visual": "optimization_visual",
        "folding_summary": "context_folding",
        "router": "router",
    }
    return mapping.get((usage_kind or "").strip(), "chat")


def medication_status_to_new(status: str | None) -> str:
    value = (status or "active").strip()
    if value == "discontinued":
        return "cancelled"
    return value


def taken_action_to_record_status(action_type: str | None) -> str:
    mapping = {
        "taken": "taken",
        "skipped": "skipped",
        "remind_later": "snoozed",
        "discontinued": "skipped",
    }
    return mapping.get((action_type or "taken").strip(), "taken")


def health_exam_type_to_new(exam_type: str | None) -> int:
    text = (exam_type or "").strip().lower()
    if text in {"special", "专项体检"}:
        return 3
    if text in {"senior"}:
        return 4
    if text in {"onboarding", "pre_employment", "入职体检"}:
        return 2
    return 1


def health_item_flag(status: str | None) -> str:
    mapping = {"normal": "", "high": "high", "low": "low", "abnormal": "abnormal", "unknown": ""}
    return mapping.get((status or "").strip(), "")


def reminder_times_from_legacy(times: Any) -> list[dict]:
    parsed = parse_json_value(times, default=[])
    if not isinstance(parsed, list):
        return []
    result: list[dict] = []
    for item in parsed:
        if isinstance(item, dict) and item.get("time"):
            result.append({"time": str(item["time"]), "dose": item.get("dose", 1)})
        elif isinstance(item, str) and item.strip():
            result.append({"time": item.strip(), "dose": 1})
    return result


def to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt.replace("%f", "000000"))], fmt.replace(".%f", "")).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def combine_reference_range(ref_low: Any, ref_high: Any, ref_text: Any) -> str:
    if ref_text:
        return str(ref_text)
    parts = []
    if ref_low is not None and str(ref_low) != "":
        parts.append(str(ref_low))
    if ref_high is not None and str(ref_high) != "":
        if parts:
            parts.append("-")
        parts.append(str(ref_high))
    return "".join(parts)


def parse_duration(duration: str | None) -> tuple[int | None, str, str]:
    text = (duration or "").strip()
    if not text:
        return None, "", text
    match = re.match(r"^(\d+)\s*(天|日|周|月|hour|hours|day|days|week|weeks|month|months)?", text, re.I)
    if not match:
        return None, "", text
    value = int(match.group(1))
    unit_raw = (match.group(2) or "天").lower()
    unit_map = {"天": "day", "日": "day", "周": "week", "月": "month", "day": "day", "days": "day", "week": "week", "weeks": "week", "month": "month", "months": "month", "hour": "hour", "hours": "hour"}
    return value, unit_map.get(unit_raw, "day"), text


LEGACY_ATTACHMENT_BUSINESS_TYPE_KEYS = {
    "avatar",
    "document",
    "medicalrecord",
    "report",
    "examreport",
    "examimaging",
    "healthexam",
    "prescriptionbatch",
    "medication",
}


def normalize_business_type_key(value: str | None) -> str:
    """Normalize legacy attachment business type spellings."""
    return re.sub(r"[\s_-]+", "", (value or "").strip().lower())


def map_business_relations(old_type: str | None, old_id: Any, id_map) -> list[tuple[str, str]]:
    key = normalize_business_type_key(old_type)
    if not old_id:
        return []

    def mapped(entity_type: str, business_type: str) -> tuple[str, str] | None:
        new_id = id_map.get(entity_type, old_id)
        if new_id:
            return business_type, str(new_id)
        return None

    if key == "avatar":
        relation = mapped("patient", "member")
        return [relation] if relation else []
    if key in {"document", "medicalrecord"}:
        relation = mapped("medical_record", "medical_case")
        return [relation] if relation else []
    if key in {"report", "examreport"}:
        relations = [
            relation
            for relation in (
                mapped("exam_report", "examination_report"),
                mapped("health_exam_hdr", "health_exam_report"),
            )
            if relation
        ]
        return relations
    if key == "examimaging":
        relation = mapped("exam_imaging_report", "examination_report")
        return [relation] if relation else []
    if key == "healthexam":
        relation = mapped("health_exam_hdr", "health_exam_report")
        return [relation] if relation else []
    if key == "prescriptionbatch":
        relation = mapped("prescription_batch", "prescription_batch")
        return [relation] if relation else []
    if key == "medication":
        relations = [
            relation
            for relation in (
                mapped("medication", "medication_plan"),
                mapped("medicine_box", "medicine_box"),
            )
            if relation
        ]
        return relations
    text = (old_type or "").strip().lower()
    return [(text or "temp", str(old_id))]


def map_business_type(old_type: str | None, old_id: Any, id_map) -> tuple[str, str] | None:
    relations = map_business_relations(old_type, old_id, id_map)
    return relations[0] if relations else None


def chat_role_to_new(role: str | None) -> str:
    value = (role or "user").strip().lower()
    if value == "search":
        return "user"
    if value in {"user", "assistant", "system"}:
        return value
    return "user"


def chat_sync_timestamp(value) -> str:
    dt = aware_datetime(value)
    if dt is None:
        dt = timezone.now()
    return dt.isoformat()


def normalize_legacy_chat_attachment(att: Any) -> dict[str, Any]:
    """Map legacy messaging attachment JSON to ChatAttachment-compatible payload."""
    if not isinstance(att, dict):
        return {}
    legacy_id = str(att.get("id") or "").strip()
    oss_file_id = att.get("ossFileId") or att.get("oss_file_id") or att.get("file_id")
    full_url = att.get("full") or att.get("url") or att.get("thumbnailURL") or att.get("thumbnail")
    att_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"zdk-chat-att:{legacy_id or full_url or 'unknown'}"))
    raw_type = str(att.get("type") or "image").strip()
    if raw_type in {"image", "image_url", "image_base64"}:
        mapped_type = "image"
    elif raw_type == "video":
        mapped_type = "video"
    elif raw_type == "pdf":
        mapped_type = "pdf"
    else:
        mapped_type = "file"
    out: dict[str, Any] = {
        "id": att_uuid,
        "type": mapped_type,
    }
    url = full_url
    if url:
        out["url"] = url
    if isinstance(oss_file_id, int):
        out["fileId"] = oss_file_id
    elif legacy_id.isdigit():
        out["fileId"] = int(legacy_id)

    full_cache_key = att.get("fullCacheKey") or att.get("full_cache_key") or att.get("cacheKey")
    if full_cache_key:
        out["fullCacheKey"] = str(full_cache_key)

    file_md5 = att.get("fileMd5") or att.get("file_md5") or att.get("md5")
    if file_md5:
        out["fileMd5"] = str(file_md5)

    text = att.get("ocrText") or att.get("ocr_text") or att.get("text") or att.get("name") or att.get("filename")
    if text:
        out["text"] = str(text)
    return out


CHAT_BLOCK_PAYLOAD_ENUM_KEYS = {
    "text": "text",
    "deepThought": "deepThought",
    "tool": "tool",
    "imageGallery": "imageGallery",
    "fileAttachments": "fileAttachments",
    "knowledgeCards": "knowledgeCards",
    "translatedText": "translatedText",
    "mapRoute": "mapRoute",
    "events": "events",
    "healthCards": "healthCards",
    "pendingMemberToolCards": "pendingMemberToolCards",
    "structuredHealthCards": "structuredHealthCards",
    "sleepVisualization": "sleepVisualization",
    "workoutVisualization": "workoutVisualization",
    "captureCard": "captureCard",
    "html": "html",
    "smallTaskCard": "smallTaskCard",
    "taskCards": "taskCards",
    "error": "error",
    "assistantStatusCard": "assistantStatusCard",
    "healthResourceReference": "healthResourceReference",
}


def chat_block_payload(
    *,
    block_id: str,
    kind: str,
    order_key: float,
    created_at,
    updated_at,
    text: str = "",
    attachments: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build ChatMessageBlock-compatible JSON for sync payloads.

    Swift encodes `ChatMessageBlockPayload.text("...")` as
    `{"text":{"_0":"..."}}`; the client requires the top-level `payload` key.
    """
    payload_extra = dict(extra or {})
    explicit_payload = payload_extra.pop("payload_value", None)
    enum_key = CHAT_BLOCK_PAYLOAD_ENUM_KEYS.get(kind, "text")

    if explicit_payload is not None:
        block_payload = {enum_key: {"_0": explicit_payload}}
    elif kind == "text":
        block_payload: dict[str, Any] = {"text": {"_0": text or ""}}
    elif kind == "imageGallery" and attachments:
        block_payload = {"imageGallery": {"_0": attachments}}
    elif kind == "fileAttachments" and attachments:
        block_payload = {"fileAttachments": {"_0": attachments}}
    elif kind == "translatedText":
        block_payload = {"translatedText": {"_0": text or ""}}
    elif kind == "html":
        block_payload = {"html": {"_0": text or ""}}
    elif kind == "error":
        block_payload = {"error": {"_0": text or ""}}
    elif kind == "deepThought":
        block_payload = {
            "deepThought": {
                "_0": {
                    "reasoningContent": text or None,
                    "reasoningDurationMs": None,
                    "reasoningExpanded": False,
                    "reasoningVisibility": "full",
                }
            }
        }
    elif kind == "tool":
        block_payload = {
            "tool": {
                "_0": {
                    "name": payload_extra.get("tool_name"),
                    "content": text or "",
                    "invocationArguments": payload_extra.get("tool_invocation_arguments"),
                }
            }
        }
    elif kind == "assistantStatusCard":
        block_payload = {
            "assistantStatusCard": {
                "_0": {
                    "type": payload_extra.get("assistant_status_type") or "sendFailed",
                    "message": text or "",
                }
            }
        }
    else:
        block_payload = {"text": {"_0": text or ""}}

    payload: dict[str, Any] = {
        "id": block_id,
        "kind": kind,
        "payload": block_payload,
        "status": "ready",
        "revision": 1,
        "order_key": order_key,
        "node_role": "timeline",
        "created_at": chat_sync_timestamp(created_at),
        "updated_at": chat_sync_timestamp(updated_at),
    }
    if kind == "text":
        payload["text"] = text or ""
    if kind in {"imageGallery", "fileAttachments"} and attachments:
        payload["attachments"] = attachments
    if payload_extra:
        payload.update(payload_extra)
    return payload


def legacy_chat_anchor_is_invalid(anchor: Any) -> bool:
    if anchor is None:
        return False
    if not isinstance(anchor, dict):
        return True
    if "type" not in anchor:
        return True
    return False


def notification_dispatch_status(old_status: str | None) -> str:
    mapping = {
        "queued": "skipped",
        "processing": "skipped",
        "sent": "sent",
        "failed": "failed",
    }
    return mapping.get((old_status or "").strip(), "skipped")
