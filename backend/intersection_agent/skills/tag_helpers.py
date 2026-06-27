"""Shared helpers for skill tag building and absorption reports."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def summarize_utterance(text: str, *, limit: int = 80) -> str:
    """Truncate user context for meta tags and recap."""
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}…"


def formula_hash(formula: str) -> str:
    """Short fingerprint for content tag comparison."""
    if not formula:
        return ""
    return hashlib.sha256(formula.encode("utf-8")).hexdigest()[:12]


def summarize_data_window_profile(data_window: dict[str, Any] | None) -> str:
    """Compact label for data window spec."""
    if not data_window:
        return "unknown"
    tier = data_window.get("source_tier") or data_window.get("tier")
    if tier:
        return str(tier)
    dow = data_window.get("dow_filter")
    if dow:
        return f"window_dow_{dow}"
    return "window_default"


def absorbed_at_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
