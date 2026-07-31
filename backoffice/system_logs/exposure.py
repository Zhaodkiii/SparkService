from datetime import date, datetime


def expose_log_value(value):
    """JSON-safe conversion without redacting sensitive fields."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): expose_log_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expose_log_value(item) for item in value]
    return value


def raw_preview(raw, limit: int = 240) -> str:
    if isinstance(raw, dict):
        text = str(raw)
    else:
        text = str(raw or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "..."
