"""Shared canonical Create-Run payload factory for run-service unit tests.

CHAT-DATA-026 removed the v1 content-only Create Run input; every test that
drives :class:`RunService.create_run` must now pass a canonical ``input_message``
with a tagged text payload.  This helper builds that shape in one place.
"""

from __future__ import annotations

import uuid
from typing import Any


def canonical_run_payload(
    thread_id: Any,
    *,
    content: str = "hello",
    client_message_id: Any = None,
    references: list | None = None,
    attachments: list | None = None,
    client: dict | None = None,
    blocks: list | None = None,
    **extra: Any,
) -> dict:
    cmid = client_message_id or uuid.uuid4()
    payload: dict[str, Any] = {
        "client_message_id": cmid,
        "capability": "chat",
        "references": references if references is not None else [],
        "attachments": attachments if attachments is not None else [],
        "client": client if client is not None else {"platform": "web", "version": "test", "device_id": "device"},
        "input_message": {
            "thread_id": str(thread_id),
            "role": "user",
            "client_message_id": str(cmid),
            "blocks": blocks
            if blocks is not None
            else [
                {
                    "kind": "text",
                    "status": "ready",
                    "revision": 1,
                    "order_key": 1000,
                    "node_role": "timeline",
                    "payload": {"text": {"_0": content}},
                }
            ],
        },
    }
    payload.update(extra)
    return payload