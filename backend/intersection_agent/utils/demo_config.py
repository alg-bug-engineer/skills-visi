"""Demo mode configuration for leadership presentation."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from intersection_agent.config import get_settings

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_DEMO_CONFIG_PATH = _BACKEND_ROOT / "config" / "demo_intersections.yaml"


@lru_cache
def load_demo_config() -> dict[str, Any]:
    """Load demo intersections YAML."""
    if not _DEMO_CONFIG_PATH.is_file():
        return {}
    with open(_DEMO_CONFIG_PATH, encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return payload.get("demo") or {}


def is_demo_mode() -> bool:
    """Whether DEMO_MODE env is enabled."""
    import os

    return os.environ.get("DEMO_MODE", "").strip().lower() in ("1", "true", "yes")


def demo_reference_date() -> date | None:
    """Fixed reference date for demo queries."""
    raw = load_demo_config().get("reference_date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def resolve_reference_date(explicit: date | None = None) -> date | None:
    """Pick reference date: explicit > demo mode anchor > None (rolling today)."""
    if explicit is not None:
        return explicit
    if is_demo_mode():
        return demo_reference_date()
    return None


def demo_intersection(inter_id: str | None) -> dict[str, Any] | None:
    """Return demo intersection entry if inter_id is in demo list."""
    if not inter_id:
        return None
    for item in load_demo_config().get("intersections") or []:
        if str(item.get("inter_id")) == str(inter_id):
            return item
    return None


def demo_meta_for_intersection(inter_id: str | None) -> dict[str, Any]:
    """Metadata attached to data_payload.meta for frontend narrative."""
    if not is_demo_mode():
        return {}
    entry = demo_intersection(inter_id)
    cfg = load_demo_config()
    payload: dict[str, Any] = {
        "demo_mode": True,
        "demo_reference_date": cfg.get("reference_date"),
        "demo_time_label": cfg.get("time_period_label"),
    }
    if entry:
        payload["demo_role"] = entry.get("role")
        payload["demo_focus_categories"] = entry.get("focus_categories") or []
        payload["demo_highlight"] = entry.get("highlight") or []
    return payload
