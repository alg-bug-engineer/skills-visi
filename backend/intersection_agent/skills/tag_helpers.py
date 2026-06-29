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


def read_hit_count(tags: dict[str, Any] | None) -> int:
    """Return persisted skill reuse counter from tags.meta."""
    if not tags:
        return 0
    meta = tags.get("meta") or {}
    try:
        return max(0, int(meta.get("hit_count") or 0))
    except (TypeError, ValueError):
        return 0


def read_last_hit_at(tags: dict[str, Any] | None) -> str | None:
    """Return ISO timestamp of last skill match hit, if recorded."""
    if not tags:
        return None
    meta = tags.get("meta") or {}
    value = meta.get("last_hit_at")
    return str(value) if value else None


def merge_usage_meta(
    existing_tags: dict[str, Any] | None,
    new_tags: dict[str, Any] | None,
) -> dict[str, Any]:
    """Preserve hit_count / last_hit_at when rewriting tags on upsert."""
    merged = dict(new_tags or {})
    existing_meta = (existing_tags or {}).get("meta") or {}
    new_meta = dict(merged.get("meta") or {})
    for key in ("hit_count", "last_hit_at"):
        if key in existing_meta:
            new_meta[key] = existing_meta[key]
    merged["meta"] = new_meta
    return merged


def increment_usage_meta(tags: dict[str, Any] | None) -> dict[str, Any]:
    """Return tags with hit_count +1 and last_hit_at updated."""
    base = dict(tags or {})
    meta = dict(base.get("meta") or {})
    meta["hit_count"] = read_hit_count(base) + 1
    meta["last_hit_at"] = absorbed_at_iso()
    base["meta"] = meta
    return base
