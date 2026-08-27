"""Structured metric/log helpers for the tool and interaction control plane.

SparkService does not currently run a dedicated metrics backend. These helpers
emit stable metric names from CHAT-AI-029 so request_id/run_id/tool_call_id/
interaction_id can reconstruct a pause/resume without logging sensitive bodies.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("chat_sync.ai.metrics")


def emit_metric(name: str, **labels: Any) -> None:
    parts = " ".join(f"{key}={value}" for key, value in sorted(labels.items()) if value is not None)
    if parts:
        logger.info("metric name=%s %s", name, parts)
    else:
        logger.info("metric name=%s", name)


__all__ = ["emit_metric"]
