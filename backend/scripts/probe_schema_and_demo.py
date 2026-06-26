#!/usr/bin/env python3
"""Probe PG schema columns and rank intersections by data completeness."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from intersection_agent.config import get_settings
from intersection_agent.db.postgres import PostgresPool


TABLES = [
    ("timing_period", "dwd_ctl_inter_day_plan_period"),
    ("corridor_stop", "dws_corridor_coord_stop_mm"),
    ("corridor_group", "dws_corridor_coord_group"),
    ("corridor_cfg", "dws_corridor_coord_cfg"),
    ("plan_cfg", "dwd_ctl_inter_plan_cfg"),
    ("min_green", "dws_turn_min_green_5min_mm"),
    ("inter_eval", "dws_inter_evaluation_5min_mm"),
    ("turn_sat", "dws_turn_saturation_5min_mm"),
    ("line_val", "dws_line_val_index_5min_mm"),
    ("complaint", "dwd_tfc_complaint_inter_issue"),
    ("manual_survey", "dwd_ctl_inter_manual_survey_issue"),
]


async def show_columns(pool: PostgresPool, schema: str, table: str) -> list[str]:
    rows = await pool.fetch(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        ORDER BY ordinal_position
        """,
        schema,
        table,
    )
    return [f"{r['column_name']} ({r['data_type']})" for r in rows]


async def probe_column_errors(pool: PostgresPool, fs: str) -> None:
    print("\n" + "=" * 70)
    print("1) 列名嗅探：代码 vs 真实表结构")
    print("=" * 70)

    for label, table in TABLES[:4]:
        cols = await show_columns(pool, fs, table)
        print(f"\n[{fs}.{table}] ({len(cols)} 列)")
        print("  " + ", ".join(cols[:20]))
        if len(cols) > 20:
            print(f"  ... +{len(cols) - 20} more")

    period_cols = {c.split(" ")[0] for c in await show_columns(pool, fs, "dwd_ctl_inter_day_plan_period")}
    stop_cols = {c.split(" ")[0] for c in await show_columns(pool, fs, "dws_corridor_coord_stop_mm")}

    print("\n--- 代码引用列校验 ---")
    for col in ("period_start_sec", "period_end_sec", "start_time", "end_time"):
        ok = col in period_cols
        print(f"  dwd_ctl_inter_day_plan_period.{col}: {'✓ 存在' if ok else '✗ 不存在'}")
    for col in ("direction_label", "avg_stop_count", "avg_total_stop_sec",
                "fwd_avg_total_stop_times", "rev_avg_total_stop_times"):
        ok = col in stop_cols
        print(f"  dws_corridor_coord_stop_mm.{col}: {'✓ 存在' if ok else '✗ 不存在'}")

    # sample row counts for timing period
    row = await pool.fetchrow(
        f"""
        SELECT COUNT(*) AS n,
               COUNT(DISTINCT inter_id) AS inter_cnt
        FROM {fs}.dwd_ctl_inter_day_plan_period
        WHERE is_deleted = 0
        """
    )
    print(f"\n  dwd_ctl_inter_day_plan_period 行数={row['n']}, 路口数={row['inter_cnt']}")

    row2 = await pool.fetchrow(
        f"""
        SELECT COUNT(*) AS n,
               COUNT(DISTINCT group_id) AS group_cnt
        FROM {fs}.dws_corridor_coord_stop_mm
        WHERE is_deleted = 0
        """
    )
    print(f"  dws_corridor_coord_stop_mm 行数={row2['n']}, 协调组数={row2['group_cnt']}")


async def rank_demo_intersections(pool: PostgresPool, fs: str, rs: str) -> None:
    print("\n" + "=" * 70)
    print("2) 演示路口推荐：按数据完备度打分")
    print("=" * 70)

    sql = f"""
    WITH base AS (
        SELECT i.inter_id, i.inter_name
        FROM {rs}.dim_inter_info i
        WHERE i.version_id = '20260501'
    ),
    scores AS (
        SELECT
            b.inter_id,
            b.inter_name,
            EXISTS (
                SELECT 1 FROM {fs}.dws_inter_evaluation_5min_mm e
                WHERE e.inter_id = b.inter_id AND e.is_deleted = 0 LIMIT 1
            )::int AS has_eval,
            EXISTS (
                SELECT 1 FROM {fs}.dws_turn_saturation_5min_mm t
                WHERE t.inter_id = b.inter_id AND t.is_deleted = 0 LIMIT 1
            )::int AS has_turn_sat,
            EXISTS (
                SELECT 1 FROM {fs}.dwd_ctl_inter_plan_cfg p
                WHERE p.inter_id = b.inter_id AND p.is_deleted = 0 LIMIT 1
            )::int AS has_plan,
            EXISTS (
                SELECT 1 FROM {fs}.dwd_ctl_inter_day_plan_period dp
                WHERE dp.inter_id = b.inter_id AND dp.is_deleted = 0 LIMIT 1
            )::int AS has_period,
            EXISTS (
                SELECT 1 FROM {fs}.dws_turn_min_green_5min_mm mg
                WHERE mg.inter_id = b.inter_id AND mg.is_deleted = 0 LIMIT 1
            )::int AS has_min_green,
            EXISTS (
                SELECT 1 FROM {rs}.dim_line_inter_rltn lr
                WHERE lr.inter_id = b.inter_id LIMIT 1
            )::int AS has_line,
            EXISTS (
                SELECT 1 FROM {fs}.dws_corridor_coord_group g
                WHERE g.is_deleted = 0
                  AND g.inter_ids_json::text LIKE '%' || b.inter_id || '%'
                LIMIT 1
            )::int AS has_corridor,
            EXISTS (
                SELECT 1 FROM {fs}.dwd_tfc_complaint_inter_issue c
                WHERE c.inter_id = b.inter_id AND c.is_deleted = 0 LIMIT 1
            )::int AS has_complaint,
            EXISTS (
                SELECT 1 FROM {fs}.dwd_ctl_inter_manual_survey_issue m
                WHERE m.inter_id = b.inter_id AND m.is_deleted = 0 LIMIT 1
            )::int AS has_survey
        FROM base b
    )
    SELECT *,
           (has_eval + has_turn_sat + has_plan + has_period + has_min_green
            + has_line + has_corridor + has_complaint + has_survey) AS score
    FROM scores
    WHERE (has_eval + has_turn_sat + has_plan) >= 2
    ORDER BY score DESC, has_corridor DESC, has_line DESC, inter_name
    LIMIT 25
  """
    rows = await pool.fetch(sql)

    print(f"\n{'分数':>4}  {'路口名':<40}  inter_id")
    print("-" * 90)
    for r in rows:
        flags = []
        if r["has_eval"]:
            flags.append("eval")
        if r["has_turn_sat"]:
            flags.append("turn")
        if r["has_plan"]:
            flags.append("plan")
        if r["has_period"]:
            flags.append("period")
        if r["has_min_green"]:
            flags.append("mingreen")
        if r["has_line"]:
            flags.append("line")
        if r["has_corridor"]:
            flags.append("corridor")
        if r["has_complaint"]:
            flags.append("complaint")
        if r["has_survey"]:
            flags.append("survey")
        print(
            f"{r['score']:>4}  {str(r['inter_name'])[:38]:<40}  {r['inter_id']}"
            f"  [{','.join(flags)}]"
        )

    # Check user's intersection
    for name in ("奥体中路", "新泺大街", "奥体西路", "经十路"):
        hits = await pool.fetch(
            f"""
            SELECT inter_id, inter_name FROM {rs}.dim_inter_info
            WHERE version_id = '20260501'
              AND inter_name LIKE '%' || $1 || '%'
            ORDER BY inter_name LIMIT 8
            """,
            name,
        )
        if hits:
            print(f"\n含「{name}」的路口 ({len(hits)} 条示例):")
            for h in hits[:5]:
                sc = await pool.fetchrow(
                    f"""
                    SELECT
                      EXISTS(SELECT 1 FROM {fs}.dwd_ctl_inter_day_plan_period dp
                             WHERE dp.inter_id=$1 AND dp.is_deleted=0 LIMIT 1) AS has_period,
                      EXISTS(SELECT 1 FROM {fs}.dws_corridor_coord_group g
                             WHERE g.is_deleted=0 AND g.inter_ids_json::text LIKE '%'||$1||'%' LIMIT 1) AS has_corridor
                    """,
                    h["inter_id"],
                )
                print(
                    f"  {h['inter_name']} ({h['inter_id']}) "
                    f"period={'Y' if sc['has_period'] else 'N'} "
                    f"corridor={'Y' if sc['has_corridor'] else 'N'}"
                )


async def main() -> None:
    settings = get_settings()
    if settings.mock_db:
        print("MOCK_DB=1，跳过")
        return

    pool = PostgresPool()
    await pool.connect()
    fs = settings.pg_flow_schema
    rs = settings.pgschema

    await probe_column_errors(pool, fs)
    await rank_demo_intersections(pool, fs, rs)
    await pool.close()
    print("\n✅ 嗅探完成")


if __name__ == "__main__":
    asyncio.run(main())
