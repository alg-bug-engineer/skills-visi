"""Sniff PostgreSQL for intersections with signal plan timing coverage."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT, Settings

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "pg_signal_coverage.json"


def sniff_signal_coverage(settings: Settings, *, limit: int = 50) -> list[dict[str, Any]]:
    """Return intersections that have plan_cfg + stage_timing rows in PG."""
    if not settings.pg_dsn:
        return []

    from app.data.pg_client import read_pg_rows

    flow = settings.pg_flow_schema
    road = settings.pg_schema
    inter_table = settings.pg_dim_inter_table

    sql = f"""
        SELECT p.inter_id,
               i.inter_name,
               COUNT(DISTINCT t.stage_no) AS stage_cnt,
               COUNT(*) AS timing_rows
        FROM {flow}.dwd_ctl_inter_plan_cfg p
        JOIN {flow}.dwd_ctl_inter_plan_stage_timing t
          ON t.inter_id = p.inter_id AND t.plan_no = p.plan_no
        JOIN {road}.{inter_table} i ON i.inter_id = p.inter_id
        WHERE i.is_signalized = 1
        GROUP BY p.inter_id, i.inter_name
        HAVING COUNT(DISTINCT t.stage_no) >= 2
        ORDER BY timing_rows DESC
    """
    rows = read_pg_rows(sql, {}, limit=limit)
    logger.info("PG 配时嗅探完成 count=%d", len(rows))
    return rows


def save_coverage(rows: list[dict[str, Any]], path: Path | None = None) -> Path:
    target = path or DEFAULT_OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "count": len(rows),
        "intersections": rows,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_coverage(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or DEFAULT_OUTPUT
    if not target.exists():
        return []
    data = json.loads(target.read_text(encoding="utf-8"))
    return list(data.get("intersections") or [])


def pick_sample_intersection(path: Path | None = None) -> dict[str, Any] | None:
    rows = load_coverage(path)
    return rows[0] if rows else None


if __name__ == "__main__":
    from dotenv import load_dotenv

    from app.config import get_settings

    load_dotenv()
    get_settings.cache_clear()
    settings = get_settings()
    rows = sniff_signal_coverage(settings, limit=30)
    out = save_coverage(rows)
    print(f"saved {len(rows)} intersections to {out}")
