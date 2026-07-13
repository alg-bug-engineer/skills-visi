#!/usr/bin/env python3
"""全库点/线优化路口对筛选。

口径对齐 analysis/溢流路口统计优化.sql 的 direction_spacing CTE，
以及 app/metrics/traffic.py 的 THRESHOLDS。

输出目录：data/screening/point-line-<timestamp>/
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.data.pg_client import read_pg_rows
from app.metrics.traffic import THRESHOLDS
from app.trace.topology import DIR8_ENTRY, TURN_LABEL, exit_dir8_for_turn, movement_label

ROOT = Path(__file__).resolve().parents[1]
OUT_BASE = ROOT / "data" / "screening"

# 时段：晚高峰 DWD 用时钟；DWS 用 step_index 204-228
PM_TIME_FILTER = "AND d.stat_time::time >= '17:00' AND d.stat_time::time < '19:00'"
PM_STEP_LO, PM_STEP_HI = 204, 228

OVERFLOW_WARN = THRESHOLDS["queue_ratio_warning"]  # 0.8
SAT_HIGH = THRESHOLDS["saturation_high"]  # 0.8
SAT_OVERSAT = THRESHOLDS["saturation_oversaturation"]  # 0.9
DOWN_SAT_HIGH = THRESHOLDS["downstream_saturation_high"]  # 0.85
GREEN_HIGH = THRESHOLDS["green_utilization_high"]  # 0.85

def ser(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: ser(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [ser(x) for x in obj]
    return obj


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ser(data), ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_direction_spacing() -> list[dict[str, Any]]:
    return read_pg_rows(
        """
        WITH direction_spacing AS (
            SELECT w.inter_id,
                   (CAST(w.dir8_code AS INTEGER) + 1) AS eight_direction,
                   MIN(l.length_m) AS adjacent_inter_spacing_m
            FROM road6.dwd_tfc_rltn_wide_inter_ft_link w
            JOIN road6.dim_link_info l
              ON w.link_id = l.link_id AND l.version_id = w.version_id
            WHERE LOWER(w.link_role) = 'entrance'
            GROUP BY w.inter_id, w.dir8_code
            HAVING MIN(l.length_m) >= 50.0
        )
        SELECT ds.inter_id, di.inter_name, ds.eight_direction, ds.adjacent_inter_spacing_m
        FROM direction_spacing ds
        LEFT JOIN road6.dim_inter_info di
          ON di.inter_id = ds.inter_id AND di.version_id = '20260501'
        ORDER BY ds.inter_id, ds.eight_direction
        """,
        {},
        limit=50000,
    )


def load_exit_downstream() -> list[dict[str, Any]]:
    """每个 (inter_id, exit_dir8) 取第一条出口 link 的下游信控路口。"""
    return read_pg_rows(
        """
        SELECT DISTINCT ON (w.inter_id, w.dir8_code)
               w.inter_id,
               di.inter_name AS inter_name,
               w.dir8_code::int AS exit_dir8,
               w.dir8_label AS exit_label,
               l.t_inter_id AS downstream_inter_id,
               down.inter_name AS downstream_inter_name,
               COALESCE(down.is_signalized, 0) AS downstream_signalized
        FROM road6.dwd_tfc_rltn_wide_inter_ft_link w
        JOIN road6.dim_link_info l
          ON l.link_id = w.link_id AND l.version_id = w.version_id
        LEFT JOIN road6.dim_inter_info di
          ON di.inter_id = w.inter_id AND di.version_id = '20260501'
        LEFT JOIN road6.dim_inter_info down
          ON down.inter_id = l.t_inter_id AND down.version_id = '20260501'
        WHERE LOWER(w.link_role) = 'exit'
          AND l.t_inter_id IS NOT NULL
          AND COALESCE(down.is_signalized, 0) = 1
        ORDER BY w.inter_id, w.dir8_code, l.length_m DESC NULLS LAST
        """,
        {},
        limit=50000,
    )


def load_turn_overflow_metrics(period: str) -> list[dict[str, Any]]:
    time_filter = PM_TIME_FILTER if period == "evening_peak" else ""
    label = "evening_peak" if period == "evening_peak" else "all_day"
    return read_pg_rows(
        f"""
        WITH direction_spacing AS (
            SELECT w.inter_id,
                   (CAST(w.dir8_code AS INTEGER) + 1) AS eight_direction,
                   MIN(l.length_m) AS adjacent_inter_spacing_m
            FROM road6.dwd_tfc_rltn_wide_inter_ft_link w
            JOIN road6.dim_link_info l
              ON w.link_id = l.link_id AND l.version_id = w.version_id
            WHERE LOWER(w.link_role) = 'entrance'
            GROUP BY w.inter_id, w.dir8_code
            HAVING MIN(l.length_m) >= 50.0
        )
        SELECT d.inter_id,
               d.eight_direction,
               d.turn_dir_no,
               ROUND(MAX(d.queue_len_avg / ds.adjacent_inter_spacing_m)::numeric, 4) AS overflow_max,
               ROUND(AVG(d.queue_len_avg / ds.adjacent_inter_spacing_m)::numeric, 4) AS overflow_mean,
               ROUND(MAX(d.queue_len_avg)::numeric, 1) AS queue_max_m,
               COUNT(*)::bigint AS sample_rows
        FROM xianchang.dwd_tfc_inter_dir_perf_5min d
        JOIN direction_spacing ds
          ON d.inter_id = ds.inter_id AND d.eight_direction = ds.eight_direction
        WHERE d.is_deleted = 0
          AND d.turn_dir_no IN (1, 2)
          {time_filter}
        GROUP BY d.inter_id, d.eight_direction, d.turn_dir_no
        """,
        {},
        limit=200000,
    )


def load_turn_saturation_metrics(period: str) -> list[dict[str, Any]]:
    step_filter = (
        f"AND s.step_index >= {PM_STEP_LO} AND s.step_index < {PM_STEP_HI}"
        if period == "evening_peak"
        else "AND s.step_index BETWEEN 0 AND 287"
    )
    return read_pg_rows(
        f"""
        SELECT s.inter_id,
               (s.dir8_code + 1) AS eight_direction,
               s.turn_dir_no,
               ROUND(MAX(s.turn_saturation)::numeric, 4) AS sat_max,
               ROUND(AVG(s.turn_saturation)::numeric, 4) AS sat_mean,
               ROUND(MAX(g.green_utilization)::numeric, 4) AS green_util_max
        FROM xianchang.dws_turn_saturation_5min_mm s
        LEFT JOIN xianchang.dws_turn_green_utilization_5min_mm g
          ON g.inter_id = s.inter_id AND g.link_id = s.link_id
         AND g.turn_dir_no = s.turn_dir_no AND g.day_of_week = s.day_of_week
         AND g.step_index = s.step_index AND g.is_deleted = 0
        WHERE s.is_deleted = 0
          AND s.turn_dir_no IN (1, 2)
          AND s.day_of_week BETWEEN 1 AND 7
          {step_filter}
        GROUP BY s.inter_id, s.dir8_code, s.turn_dir_no
        """,
        {},
        limit=200000,
    )


def eight_to_dir8(eight: int) -> int:
    return int(eight) - 1


def receiving_eight_direction(exit_dir8: int) -> int:
    return ((int(exit_dir8) + 4) % 8) + 1


def classify_pair(
    target_overflow_max: float | None,
    target_overflow_mean: float | None,
    target_sat_max: float | None,
    target_green_max: float | None,
    down_overflow_max: float | None,
    down_sat_max: float | None,
    has_down_dwd: bool,
) -> tuple[str, dict[str, Any]]:
    """返回 (screen_type, criteria_detail)。"""
    t_overflow = target_overflow_max or 0.0
    t_sat = target_sat_max or 0.0
    t_green = target_green_max or 0.0
    d_overflow = down_overflow_max if down_overflow_max is not None else None
    d_sat = down_sat_max if down_sat_max is not None else None

    target_overflow_problem = t_overflow >= OVERFLOW_WARN
    target_sat_problem = t_sat >= SAT_OVERSAT
    target_high_demand = t_sat >= SAT_HIGH and t_green >= GREEN_HIGH
    target_problem = target_overflow_problem or target_sat_problem or target_high_demand
    if target_overflow_problem:
        target_trigger = "queue_ratio_peak"
    elif target_sat_problem:
        target_trigger = "saturation_peak"
    elif target_high_demand:
        target_trigger = "saturation_and_green_peak"
    else:
        target_trigger = None

    if not has_down_dwd:
        down_blocked = None
        down_slack = None
    else:
        down_blocked = (d_overflow is not None and d_overflow >= OVERFLOW_WARN) or (
            d_sat is not None and d_sat >= DOWN_SAT_HIGH
        )
        down_slack = not down_blocked

    if target_problem and down_slack is True:
        screen_type = "TYPE1_POINT"
    elif target_problem and down_blocked is True:
        screen_type = "TYPE2_LINE"
    elif t_overflow >= 0.3 and down_slack is True:
        screen_type = "WEAK_TYPE1"
    elif t_overflow >= 0.3 and down_blocked is True:
        screen_type = "WEAK_TYPE2"
    elif target_sat_problem and t_overflow < OVERFLOW_WARN and t_green < THRESHOLDS["green_utilization_low"]:
        screen_type = "EXPORT_BLOCKED"
    elif target_problem and down_blocked is None:
        screen_type = "UNKNOWN_DOWNSTREAM"
    else:
        screen_type = "OTHER"

    return screen_type, {
        "target_overflow_problem": target_overflow_problem,
        "target_sat_problem": target_sat_problem,
        "target_high_demand": target_high_demand,
        "target_problem_trigger": target_trigger,
        "classification_statistic": "window_peak",
        "downstream_blocked": down_blocked,
        "downstream_slack": down_slack,
        "has_downstream_dwd": has_down_dwd,
    }


def build_pairs(
    spacing_rows: list[dict[str, Any]],
    exit_rows: list[dict[str, Any]],
    overflow_pm: list[dict[str, Any]],
    overflow_all: list[dict[str, Any]],
    sat_pm: list[dict[str, Any]],
    inter_names: dict[str, str],
) -> list[dict[str, Any]]:
    exit_map: dict[tuple[str, int], dict[str, Any]] = {}
    for r in exit_rows:
        key = (str(r["inter_id"]), int(r["exit_dir8"]))
        if key not in exit_map:
            exit_map[key] = r

    def metric_index(rows: list[dict[str, Any]]) -> dict[tuple[str, int, int], dict[str, Any]]:
        idx: dict[tuple[str, int, int], dict[str, Any]] = {}
        for r in rows:
            idx[(str(r["inter_id"]), int(r["eight_direction"]), int(r["turn_dir_no"]))] = r
        return idx

    ov_pm = metric_index(overflow_pm)
    ov_all = metric_index(overflow_all)
    sat_idx = metric_index(sat_pm)

    # 下游指标索引（按 inter + receiving eight_direction + turn 2 默认直行接收）
    down_ov_pm: dict[tuple[str, int, int], dict[str, Any]] = defaultdict(dict)
    for r in overflow_pm:
        down_ov_pm[(str(r["inter_id"]), int(r["eight_direction"]), int(r["turn_dir_no"]))] = r

    pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, str]] = set()

    for (iid, ed, td), pm in ov_pm.items():
        dir8 = eight_to_dir8(ed)
        exit_d8 = exit_dir8_for_turn(dir8, td)
        if exit_d8 is None:
            continue
        ex = exit_map.get((iid, exit_d8))
        if not ex:
            continue
        down_id = str(ex.get("downstream_inter_id") or "")
        if not down_id:
            continue
        dedupe = (iid, ed, td, down_id)
        if dedupe in seen:
            continue
        seen.add(dedupe)

        recv_ed = receiving_eight_direction(exit_d8)
        # 下游接收转向：直行走廊用 turn=2；左转/右转出口用同 turn
        recv_turn = td
        down_pm = down_ov_pm.get((down_id, recv_ed, recv_turn))
        down_sat = sat_idx.get((down_id, recv_ed, recv_turn))

        all_m = ov_all.get((iid, ed, td), {})
        sat_m = sat_idx.get((iid, ed, td), {})

        t_ov_max = float(pm.get("overflow_max") or 0)
        t_ov_mean = float(pm.get("overflow_mean") or 0)
        t_sat = float(sat_m.get("sat_max") or 0) if sat_m else 0.0
        t_green = float(sat_m.get("green_util_max") or 0) if sat_m else 0.0
        d_ov = float(down_pm.get("overflow_max")) if down_pm and down_pm.get("overflow_max") is not None else None
        d_sat = float(down_sat.get("sat_max")) if down_sat and down_sat.get("sat_max") is not None else None

        screen_type, criteria = classify_pair(
            t_ov_max, t_ov_mean, t_sat, t_green, d_ov, d_sat, has_down_dwd=down_pm is not None
        )
        pairs.append(
            {
                "target_inter_id": iid,
                "target_inter_name": inter_names.get(iid) or ex.get("inter_name"),
                "movement": movement_label(dir8, td),
                "entrance_dir8": dir8,
                "entrance_eight_direction": ed,
                "turn_dir_no": td,
                "exit_dir8": exit_d8,
                "downstream_inter_id": down_id,
                "downstream_inter_name": ex.get("downstream_inter_name"),
                "receiving_eight_direction": recv_ed,
                "receiving_turn_dir_no": recv_turn,
                "period": "evening_peak",
                "target_overflow_max_pm": t_ov_max,
                "target_overflow_mean_pm": t_ov_mean,
                "target_overflow_max_all": float(all_m.get("overflow_max") or 0) if all_m else None,
                "target_sat_max_pm": t_sat or None,
                "target_green_util_max_pm": t_green or None,
                "target_queue_max_m_pm": float(pm.get("queue_max_m") or 0) if pm.get("queue_max_m") else None,
                "downstream_overflow_max_pm": d_ov,
                "downstream_sat_max_pm": d_sat,
                "screen_type": screen_type,
                **criteria,
            }
        )

    return pairs


def main() -> None:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = OUT_BASE / f"point-line-{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading direction_spacing...")
    spacing = load_direction_spacing()
    write_json(out_dir / "intermediate_01_direction_spacing.json", spacing)
    write_csv(out_dir / "intermediate_01_direction_spacing.csv", ser(spacing))

    print("Loading exit->downstream topology...")
    exits = load_exit_downstream()
    write_json(out_dir / "intermediate_02_exit_downstream.json", exits)
    write_csv(out_dir / "intermediate_02_exit_downstream.csv", ser(exits))

    print("Loading turn overflow metrics (evening peak)...")
    ov_pm = load_turn_overflow_metrics("evening_peak")
    write_json(out_dir / "intermediate_03_turn_overflow_evening_peak.json", ov_pm)

    print("Loading turn overflow metrics (all day)...")
    ov_all = load_turn_overflow_metrics("all_day")
    write_json(out_dir / "intermediate_04_turn_overflow_all_day.json", ov_all)

    print("Loading turn saturation (evening peak)...")
    sat_pm = load_turn_saturation_metrics("evening_peak")
    write_json(out_dir / "intermediate_05_turn_saturation_evening_peak.json", sat_pm)

    inter_names = {str(r["inter_id"]): r.get("inter_name") for r in spacing if r.get("inter_name")}

    print("Building corridor pairs...")
    pairs = build_pairs(spacing, exits, ov_pm, ov_all, sat_pm, inter_names)
    write_json(out_dir / "full_pair_screening_results.json", pairs)
    write_csv(out_dir / "full_pair_screening_results.csv", pairs)

    type1 = [p for p in pairs if p["screen_type"] in ("TYPE1_POINT", "WEAK_TYPE1")]
    type2 = [p for p in pairs if p["screen_type"] in ("TYPE2_LINE", "WEAK_TYPE2")]
    type1_strong = [p for p in pairs if p["screen_type"] == "TYPE1_POINT"]
    type2_strong = [p for p in pairs if p["screen_type"] == "TYPE2_LINE"]
    # 严格典型点优化：目标必须由同进口同转向排队比峰值触发，不能仅由
    # 饱和度峰值或“路口 MAX 排队 / 其他进口库容”代理触发；下游仍使用
    # 真实接收进口道同转向排队判定承接空间。
    strict_type1_overflow = [
        p
        for p in pairs
        if p["screen_type"] == "TYPE1_POINT"
        and p.get("target_overflow_problem") is True
        and p.get("downstream_slack") is True
    ]

    type1.sort(key=lambda x: (-(x.get("target_overflow_max_pm") or 0), -(x.get("target_sat_max_pm") or 0)))
    type2.sort(key=lambda x: (-(x.get("target_overflow_max_pm") or 0), -(x.get("downstream_sat_max_pm") or 0)))
    strict_type1_overflow.sort(
        key=lambda x: (
            -(x.get("target_overflow_mean_pm") or 0),
            -(x.get("target_overflow_max_pm") or 0),
        )
    )

    write_json(out_dir / "type1_candidates.json", type1)
    write_csv(out_dir / "type1_candidates.csv", type1)
    write_json(out_dir / "type2_candidates.json", type2)
    write_csv(out_dir / "type2_candidates.csv", type2)
    write_json(out_dir / "type1_strong_candidates.json", type1_strong)
    write_json(out_dir / "type2_strong_candidates.json", type2_strong)
    write_json(out_dir / "strict_type1_overflow_candidates.json", strict_type1_overflow)
    write_csv(out_dir / "strict_type1_overflow_candidates.csv", strict_type1_overflow)

    # 路口级去重汇总
    by_type: dict[str, set[str]] = defaultdict(set)
    for p in pairs:
        by_type[p["screen_type"]].add(p["target_inter_id"])

    summary = {
        "generated_at": datetime.now().isoformat(),
        "output_dir": str(out_dir.relative_to(ROOT)),
        "sql_source": "analysis/溢流路口统计优化.sql",
        "thresholds": THRESHOLDS,
        "classification_policy": "peak_first_demo_v1",
        "period": "evening_peak 17:00-19:00 (DWD clock / DWS step 204-228)",
        "counts": {
            "direction_spacing_rows": len(spacing),
            "exit_downstream_rows": len(exits),
            "turn_overflow_pm_rows": len(ov_pm),
            "corridor_pairs_total": len(pairs),
            "type1_strong": len(type1_strong),
            "type1_with_weak": len(type1),
            "type2_strong": len(type2_strong),
            "type2_with_weak": len(type2),
            "strict_type1_overflow": len(strict_type1_overflow),
            "unknown_downstream": sum(1 for p in pairs if p["screen_type"] == "UNKNOWN_DOWNSTREAM"),
            "other": sum(1 for p in pairs if p["screen_type"] == "OTHER"),
        },
        "unique_intersections_by_type": {k: sorted(v) for k, v in by_type.items()},
    }
    write_json(out_dir / "screening_summary.json", summary)

    # 写说明文档
    readme = out_dir / "README.md"
    readme.write_text(
        f"""# 点/线优化路口全库筛选结果

生成时间：{summary['generated_at']}

## 文件说明

| 文件 | 说明 |
|------|------|
| `intermediate_01_direction_spacing.*` | 进口道相邻间距（SQL 口径） |
| `intermediate_02_exit_downstream.*` | 出口 link → 下游信控路口拓扑 |
| `intermediate_03_turn_overflow_evening_peak.json` | 转向级晚高峰溢流比 max/mean |
| `intermediate_04_turn_overflow_all_day.json` | 转向级全天溢流比 |
| `intermediate_05_turn_saturation_evening_peak.json` | 转向级晚高峰饱和度/绿灯利用率 |
| `full_pair_screening_results.*` | **全量** 目标-下游走廊配对及分型 |
| `type1_candidates.*` | Type1 点优化（含 WEAK） |
| `type2_candidates.*` | Type2 线优化（含 WEAK） |
| `type1_strong_candidates.json` | 峰值口径 Type1（溢流峰值或饱和度峰值触发，下游有空间） |
| `type2_strong_candidates.json` | 峰值口径 Type2（目标峰值触发且下游 blocked） |
| `strict_type1_overflow_candidates.*` | 严格点优化典型：目标真实转向溢流且下游真实接收转向可承接 |
| `screening_summary.json` | 汇总统计 |

详细方法论见 `archive/docs/点线优化路口筛选分析.md`。

## 本次扫描统计

- 走廊配对总数：{summary['counts']['corridor_pairs_total']}
- 峰值口径 Type1：{summary['counts']['type1_strong']}
- 峰值口径 Type2：{summary['counts']['type2_strong']}
- 严格溢流型 Type1：{summary['counts']['strict_type1_overflow']}
- 下游缺 DWD：{summary['counts']['unknown_downstream']}
""",
        encoding="utf-8",
    )

    # 最新结果软链目录
    latest = OUT_BASE / "point-line-latest"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to(out_dir.name)

    print(f"Done. Output: {out_dir}")
    print(json.dumps(summary["counts"], indent=2))


if __name__ == "__main__":
    main()
