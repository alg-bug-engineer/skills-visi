"""Logging helper functions."""

from __future__ import annotations

import json
import logging
from typing import Any

from intersection_agent.logging.context import get_request_id

REDACT_KEYS = frozenset(
    {"password", "api_key", "dashscope_api_key", "pgpassword", "authorization"}
)


def safe_preview(value: Any, max_len: int = 500) -> str:
    """Convert value to truncated string safe for logs."""
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            text = str(value)
    else:
        text = str(value)
    text = _redact_text(text)
    if len(text) > max_len:
        return f"{text[:max_len]}…({len(text)} chars)"
    return text


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: Any,
) -> None:
    """Emit a structured single-line log event."""
    parts = [f"event={event}", f"req={get_request_id()}"]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={safe_preview(value, max_len=300)}")
    logger.log(level, " | ".join(parts))


def _redact_text(text: str) -> str:
    """Best-effort redaction of secrets in log strings."""
    lowered = text.lower()
    for key in REDACT_KEYS:
        if key in lowered:
            return "[REDACTED]"
    return text
