"""Pure provider-error classifiers used by later request degradation."""

from __future__ import annotations


def error_text(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    body = getattr(exc, "body", None) or getattr(exc, "doc", None) or getattr(response, "text", None) or getattr(exc, "message", None) or str(exc)
    return str(body).lower()


def is_stream_options_unsupported(exc: Exception) -> bool:
    return any(marker in error_text(exc) for marker in ("stream_options", "stream options", "unknown parameter", "unrecognized request argument", "unsupported parameter", "extra inputs are not permitted", "unexpected keyword"))


def is_tool_schema_unsupported(exc: Exception) -> bool:
    return any(marker in error_text(exc) for marker in ("tool", "function_declaration", "function declaration", "function_declarations", "tool_choice", "parameters.properties", "404_not_found", "404 not_found"))


def is_image_input_unsupported(exc: Exception) -> bool:
    return any(marker in error_text(exc) for marker in ("image", "vision", "multimodal", "image_url", "content type", "must be a string", "expected a string", "expected string", "invalid type for 'messages"))


__all__ = ["error_text", "is_image_input_unsupported", "is_stream_options_unsupported", "is_tool_schema_unsupported"]

