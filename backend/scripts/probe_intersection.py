#!/usr/bin/env python3
"""Probe PostgreSQL for 奥体西路 × 经十路 intersection variants and DWS metrics."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Load backend/.env
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from intersection_agent.config import get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.services.intersection_resolver import IntersectionResolver
from intersection_agent.utils.data_window import build_data_window
from intersection_agent.models.domain import TimePeriod


VARIANTS = [
    "奥体西路与经十路交叉口",
    "经十路与奥体西路交叉口",
    "奥体西路与经十路路口",
    "经十路与奥体西路路口",
    "奥体西与经十路",
    "经十路和奥体西",
    "奥体西路经十路路口",
]

PERIODS = [
    ("早高峰", TimePeriod(start="07:00", end="09:00", label="早高峰")),
    ("晚高峰", TimePeriod(start="16:00", end="18:00", label="晚高峰")),
    ("平峰", TimePeriod(start="10:00", end="11:00", label="平峰")),
]


async def probe_metrics(pool: PostgresPool, inter_id: str, tp: TimePeriod) -> dict:
    """Fetch summary metrics for a time period."""
    settings = get_settings()
    window = build_data_window(tp)
    fs = settings.pg_flow_schema

    eval_row = await pool.fetchrow(
        f"""
        SELECT AVG(saturation_max) AS saturation_max,
               AVG(unbalance_index) AS imbalance_index
        FROM {fs}.dws_inter_evaluation_5min_mm
        WHERE inter_id = $1 AND day_of_week = ANY($2::int[])
          AND step_index BETWEEN $3 AND $4 AND is_deleted = 0
        """,
        inter_id,
        list(window.dow_filter),
        window.step_start,
        window.step_end,
    )
    sat_row = await pool.fetchrow(
        f"""
        SELECT MAX(turn_saturation) AS turn_saturation
        FROM {fs}.dws_turn_saturation_5min_mm
        WHERE inter_id = $1 AND day_of_week = ANY($2::int[])
          AND step_index BETWEEN $3 AND $4 AND is_deleted = 0
        """,
        inter_id,
        list(window.dow_filter),
        window.step_start,
        window.step_end,
    )
    plan_row = await pool.fetchrow(
        f"""
        SELECT AVG(cycle_len_sec) AS cycle_length
        FROM {fs}.dwd_ctl_inter_plan_cfg
        WHERE inter_id = $1 AND is_deleted = 0
        """,
        inter_id,
    )
    return {
        "saturation_max": float(eval_row["saturation_max"] or 0) if eval_row else None,
        "imbalance_index": float(eval_row["imbalance_index"] or 0) if eval_row else None,
        "turn_saturation": float(sat_row["turn_saturation"] or 0) if sat_row else None,
        "cycle_length": float(plan_row["cycle_length"] or 0) if plan_row else None,
        "data_window": window.to_meta(),
        "step_range": f"{window.step_start}-{window.step_end}",
    }


async def main() -> None:
    """Run intersection resolution and DWS probe."""
    settings = get_settings()
    if settings.mock_db:
        print("WARN: MOCK_DB=1，跳过真实数据库嗅探")
        return

    pool = PostgresPool()
    await pool.connect()
    resolver = IntersectionResolver(pool=pool)

    print("=" * 60)
    print("路口名称变体解析嗅探（奥体西路 × 经十路）")
    print("=" * 60)

    canonical_id: str | None = None
    canonical_name: str | None = None

    for name in VARIANTS:
        result = await resolver.resolve(name)
        print(f"\n输入: {name}")
        print(f"  source={result.source}")
        print(f"  inter_id={result.inter_id}")
        print(f"  inter_name={result.inter_name}")
        if result.candidates:
            print(f"  candidates={result.candidates}")
        if result.inter_id and not canonical_id:
            canonical_id = result.inter_id
            canonical_name = result.inter_name

    if not canonical_id:
        print("\n❌ 未能解析到有效路口，请检查 dim_inter_info 数据")
        await pool.close()
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"DWS 指标嗅探 · {canonical_name} ({canonical_id})")
    print("=" * 60)

    for label, tp in PERIODS:
        metrics = await probe_metrics(pool, canonical_id, tp)
        print(f"\n[{label}] step_index={metrics['step_range']}")
        for k, v in metrics.items():
            if k != "step_range":
                print(f"  {k}: {v}")

    await pool.close()
    print("\n✅ 嗅探完成")


if __name__ == "__main__":
    asyncio.run(main())
