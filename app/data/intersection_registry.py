"""Intersection name → inter_id registry (fixture-backed; PG lookup in follow-up)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FIXTURES_ROOT = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", name or "").strip()


def load_registry() -> dict[str, dict[str, Any]]:
    path = FIXTURES_ROOT / "intersection_registry.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {_normalize_name(k): {**v, "inter_name": v.get("inter_name", k)} for k, v in raw.items()}


def resolve_intersection(
    intersection_name: str | None,
    *,
    inter_id: str | None = None,
) -> dict[str, Any] | None:
    """Resolve intersection record by id or fuzzy name match."""
    registry = load_registry()
    if inter_id:
        for record in registry.values():
            if str(record.get("inter_id")) == str(inter_id):
                return record

    if not intersection_name:
        return None

    key = _normalize_name(intersection_name)
    if key in registry:
        return registry[key]

    for norm_name, record in registry.items():
        if key in norm_name or norm_name in key:
            return record

    logger.info("路口未在注册表命中 name=%s", intersection_name)
    return None


def enrich_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    """Attach inter_id and coordinates when resolvable."""
    enriched = dict(ticket)
    record = resolve_intersection(
        enriched.get("intersection_name"),
        inter_id=enriched.get("inter_id"),
    )
    if not record:
        return enriched
    enriched.setdefault("inter_id", record.get("inter_id"))
    if record.get("lng") is not None:
        enriched.setdefault("lng", record["lng"])
    if record.get("lat") is not None:
        enriched.setdefault("lat", record["lat"])
    return enriched
