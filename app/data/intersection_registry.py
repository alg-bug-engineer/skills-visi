"""Intersection name → inter_id registry with PG lookup for production."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FIXTURES_ROOT = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"


def fixture_registry_enabled() -> bool:
    """Fixture registry is for tests and explicit demo mode only."""
    from app.config import get_settings

    settings = get_settings()
    return bool(settings.allow_demo_fallback or not settings.pg_dsn)


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", name or "").strip()


def load_registry() -> dict[str, dict[str, Any]]:
    if not fixture_registry_enabled():
        return {}
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
    """Resolve intersection record by id or fuzzy name match (PG first in production)."""
    if inter_id:
        pg_record = _resolve_from_pg(inter_id=inter_id)
        if pg_record:
            return pg_record
        registry = load_registry()
        for record in registry.values():
            if str(record.get("inter_id")) == str(inter_id):
                record = dict(record)
                record.setdefault("source", "fixture")
                return record

    if not intersection_name:
        return None

    pg_record = _resolve_from_pg(inter_name=intersection_name)
    if pg_record:
        return pg_record

    registry = load_registry()
    key = _normalize_name(intersection_name)
    if key in registry:
        record = dict(registry[key])
        record.setdefault("source", "fixture")
        return record

    for norm_name, record in registry.items():
        if key in norm_name or norm_name in key:
            matched = dict(record)
            matched.setdefault("source", "fixture")
            return matched

    logger.info("路口未在 PG/注册表命中 name=%s inter_id=%s", intersection_name, inter_id)
    return None


@lru_cache(maxsize=256)
def _resolve_from_pg(
    *,
    inter_id: str | None = None,
    inter_name: str | None = None,
) -> dict[str, Any] | None:
    from app.config import get_settings

    settings = get_settings()
    if not settings.pg_dsn:
        return None

    try:
        from app.data.pg_client import read_pg_rows
    except Exception:
        return None

    version_sql = (
        f"(SELECT version_id FROM {settings.pg_schema}.dim_data_version "
        "WHERE is_enable = 1 LIMIT 1)"
    )
    table = settings.pg_dim_inter_table
    schema = settings.pg_schema

    if inter_id:
        sql = f"""
            SELECT inter_id, inter_name, geom_center
            FROM {schema}.{table}
            WHERE version_id = {version_sql}
              AND inter_id = %(inter_id)s
            LIMIT 1
        """
        params = {"inter_id": inter_id}
    elif inter_name:
        sql = f"""
            SELECT inter_id, inter_name, geom_center
            FROM {schema}.{table}
            WHERE version_id = {version_sql}
              AND is_signalized = 1
              AND inter_name LIKE %(pattern)s
            ORDER BY LENGTH(inter_name)
            LIMIT 1
        """
        params = {"pattern": f"%{inter_name}%"}
    else:
        return None

    try:
        rows = read_pg_rows(sql, params, limit=1)
    except Exception as exc:
        logger.warning("PG 路口解析失败 inter_id=%s name=%s err=%s", inter_id, inter_name, exc)
        return None

    if not rows:
        return None

    row = rows[0]
    lng, lat = _parse_geom_center(row.get("geom_center"))
    return {
        "inter_id": row.get("inter_id"),
        "inter_name": row.get("inter_name"),
        "lng": lng,
        "lat": lat,
        "source": "pg",
    }


def _parse_geom_center(geom_center: Any) -> tuple[float | None, float | None]:
    if not geom_center:
        return None, None
    text = str(geom_center)
    match = re.search(r"([-\d.]+)[,\s]+([-\d.]+)", text)
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))


def enrich_ticket(ticket: dict[str, Any], *, user_input: str = "") -> dict[str, Any]:
    """Attach inter_id and coordinates when resolvable (fixture or PG matcher)."""
    from app.data.intersection_matcher import enrich_ticket_with_match

    return enrich_ticket_with_match(ticket, user_input=user_input)
