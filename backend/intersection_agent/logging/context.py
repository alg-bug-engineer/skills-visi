"""Request-scoped logging context."""

from __future__ import annotations

import contextvars
import uuid

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def set_request_id(value: str | None = None) -> str:
    """Set current request id; generate UUID if omitted."""
    rid = value or str(uuid.uuid4())
    _request_id.set(rid)
    return rid


def get_request_id() -> str:
    """Return current request id."""
    return _request_id.get()
