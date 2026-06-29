#!/usr/bin/env python3
"""P0 探针：筛选「有分向饱和度 + 有上游溯源 + 高饱和」的演示候选路口。

用途：流量溯源接入问题诊断（docs/plans/2026-06-29-流量溯源接入问题诊断-开发计划.md）的 T0.1/T0.3。
口径：晚高峰、工作日；溯源取最新 month；一跳锁定 = 同上游方位取 path_coverage 最大者。

运行（需 backend/.env 且 MOCK_DB=0）：
    cd backend && .venv/bin/python scripts/probe_flow_trace.py
    cd backend && .venv/bin/python scripts/probe_flow_trace.py --inter 011wwe28ctu00001
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from intersection_agent.config import get_settings  # noqa: E402
from intersection_agent.db.postgres import PostgresPool  # noqa: E402
from intersection_agent.models.domain import TimePeriod  # noqa: E402
from intersection_agent.utils.data_window import build_data_window  # noqa: E402

DIR8_LABELS = {
    0: "北进口", 1: "东北进口", 2: "东进口", 3: "东南进口",
    4: "南进口", 5: "西南进口", 6: "西进口", 7: "西北进口",
}
TURN_LABELS = {1: "左转", 2: "直行", 3: "右转", 4: "掉头"}
EVENING = TimePeriod(start="16:00", end="18:00", label="晚高峰")
HIGH_SAT = 0.80
OVERSAT = 0.90


def _movement(dir8: int, turn: int) -> str:
    return f"{DIR8_LABELS.get(dir8, str(dir8))}{TURN_LABELS.get(turn, str(turn))}"


async def _turn_saturation(pool: PostgresPool, flow_schema: str, inter_id: str) -> list[dict]:
    window = build_data_window(EVENING)
    rows = await pool.fetch(
        f"""
        SELECT dir8_code, turn_dir_no, AVG(turn_saturation) AS sat
        FROM {flow_schema}.dws_turn_saturation_5min_mm
        WHERE inter_id = $1 AND day_of_week = ANY($2::int[])
          AND step_index BETWEEN $3 AND $4 AND is_deleted = 0
        GROUP BY dir8_code, turn_dir_no
        ORDER BY sat DESC NULLS LAST
        """,
        inter_id,
        list(window.dow_filter),
        window.step_start,
        window.step_end,
    )
    return [
        {
            "dir8": int(r["dir8_code"] or 0),
            "turn": int(r["turn_dir_no"] or 2),
            "sat": float(r["sat"]) if r["sat"] is not None else None,
        }
        for r in rows
    ]


async def _upstream_trace(pool: PostgresPool, flow_schema: str, inter_id: str) -> list[dict]:
    """晚高峰 UPSTREAM 一跳来源（同上游方位取最大 coverage）。"""
    rows = await pool.fetch(
        f"""
        SELECT f_dir8_no, turn_dir_no, cor_inter_id, cor_f_dir8_no, cor_turn_dir_no,
               flow_share_ratio
        FROM {flow_schema}.dws_tfc_inter_turn_flow_correlate_m
        WHERE inter_id = $1 AND trace_type = 'UPSTREAM' AND is_deleted = 0
          AND period_type = 'EVENING_PEAK'
          AND day_of_week IN ('工作日', '周一')
          AND month = (
              SELECT MAX(m.month) FROM {flow_schema}.dws_tfc_inter_turn_flow_correlate_m m
              WHERE m.inter_id = $1 AND m.is_deleted = 0
          )
        """,
        inter_id,
    )
    # 一跳锁定：(my dir8, my turn, cor_dir8, cor_turn) 方位组取 coverage 最大
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (
            int(r["f_dir8_no"]), int(r["turn_dir_no"]),
            int(r["cor_f_dir8_no"]), int(r["cor_turn_dir_no"]),
        )
        cov = float(r["flow_share_ratio"] or 0)
        if key not in best or cov > best[key]["coverage"]:
            best[key] = {
                "my_dir8": key[0], "my_turn": key[1],
                "cor_inter_id": r["cor_inter_id"],
                "cor_dir8": key[2], "cor_turn": key[3],
                "coverage": cov,
            }
    return list(best.values())


async def probe_one(pool: PostgresPool, flow_schema: str, inter_id: str) -> dict:
    sats = await _turn_saturation(pool, flow_schema, inter_id)
    trace = await _upstream_trace(pool, flow_schema, inter_id)
    over_turns = [s for s in sats if s["sat"] is not None and s["sat"] >= OVERSAT]
    high_turns = [s for s in sats if s["sat"] is not None and s["sat"] >= HIGH_SAT]
    # 问题转向上的最强一跳来源
    by_problem = []
    for s in high_turns:
        srcs = sorted(
            [t for t in trace if t["my_dir8"] == s["dir8"] and t["my_turn"] == s["turn"]],
            key=lambda x: -x["coverage"],
        )
        if srcs:
            by_problem.append({"turn": _movement(s["dir8"], s["turn"]), "sat": s["sat"], "top": srcs[0]})
    return {
        "inter_id": inter_id,
        "turn_sat_count": len(sats),
        "high_turn_count": len(high_turns),
        "over_turn_count": len(over_turns),
        "max_sat": max((s["sat"] for s in sats if s["sat"] is not None), default=None),
        "trace_one_hop": len(trace),
        "problem_with_source": by_problem,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inter", help="只探单个 inter_id")
    parser.add_argument("--limit", type=int, default=40, help="候选扫描上限")
    args = parser.parse_args()

    settings = get_settings()
    if settings.mock_db:
        print("WARN: MOCK_DB=1，跳过真实数据库嗅探")
        return
    flow_schema = settings.pg_flow_schema
    pool = PostgresPool()
    await pool.connect()
    try:
        if args.inter:
            res = await probe_one(pool, flow_schema, args.inter)
            _print_one(res)
            return

        # 候选：在溯源表里作为基准、且有最多 UPSTREAM 行的路口
        cand_rows = await pool.fetch(
            f"""
            SELECT inter_id, COUNT(*) AS n
            FROM {flow_schema}.dws_tfc_inter_turn_flow_correlate_m
            WHERE trace_type = 'UPSTREAM' AND is_deleted = 0 AND period_type = 'EVENING_PEAK'
            GROUP BY inter_id ORDER BY n DESC LIMIT $1
            """,
            args.limit,
        )
        print(f"扫描 {len(cand_rows)} 个溯源候选路口（晚高峰 UPSTREAM 行数 TOP{args.limit}）\n")
        results = []
        for cr in cand_rows:
            res = await probe_one(pool, flow_schema, cr["inter_id"])
            results.append(res)
        # 排序：优先 过饱和转向多 + 有问题转向溯源
        results.sort(key=lambda r: (len(r["problem_with_source"]), r["over_turn_count"]), reverse=True)
        print(f"{'inter_id':<20} {'分向饱和数':>8} {'高饱和':>6} {'过饱和':>6} {'最大饱和':>8} {'一跳来源':>8} {'问题转向溯源':>10}")
        for r in results[:20]:
            ms = f"{r['max_sat']:.2f}" if r["max_sat"] is not None else "—"
            print(f"{r['inter_id']:<20} {r['turn_sat_count']:>8} {r['high_turn_count']:>6} "
                  f"{r['over_turn_count']:>6} {ms:>8} {r['trace_one_hop']:>8} {len(r['problem_with_source']):>10}")
        print("\n推荐演示路口（问题转向有溯源 + 过饱和转向最多）：")
        for r in results[:3]:
            if r["problem_with_source"]:
                ms = f"{r['max_sat']:.2f}" if r["max_sat"] is not None else "—"
                print(f"\n★ {r['inter_id']}  最大饱和={ms} 过饱和转向={r['over_turn_count']}")
                _print_one(r)
    finally:
        await pool.close()


def _print_one(res: dict) -> None:
    print(f"  路口 {res['inter_id']}: 分向饱和{res['turn_sat_count']}条 "
          f"高饱和{res['high_turn_count']} 过饱和{res['over_turn_count']} "
          f"最大饱和={res['max_sat']} 一跳来源{res['trace_one_hop']}个")
    for p in res["problem_with_source"][:6]:
        t = p["top"]
        print(f"    · {p['turn']} 饱和{p['sat']:.2f} ← 主要途经 {t['cor_inter_id']} "
              f"{_movement(t['cor_dir8'], t['cor_turn'])} {t['coverage']:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
