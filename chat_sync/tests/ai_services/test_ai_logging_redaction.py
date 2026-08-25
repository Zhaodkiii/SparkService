from common.middleware.request_logging_middleware import _headers_for_log, _redact_chat_ai_body


def test_ai_request_logging_redacts_content_references_and_credentials():
    body = _redact_chat_ai_body(
        {
            "content": "患者的完整医疗描述",
            "references": [{"type": "health_resource", "id": "secret-resource"}],
            "client": {"platform": "web"},
            "ticket": "single-use-secret",
        }
    )
    assert body["content"] == "<redacted>"
    assert body["references"] == {"count": 1}
    assert body["client"]["platform"] == "web"
    assert body["ticket"] == "<redacted>"

    headers = _headers_for_log(
        {"Authorization": "Bearer secret", "Idempotency-Key": "private-key", "Content-Type": "application/json"},
        redact_sensitive=True,
    )
    assert headers["Authorization"] == "<redacted>"
    assert headers["Idempotency-Key"] == "<redacted>"
    assert headers["Content-Type"] == "application/json"
