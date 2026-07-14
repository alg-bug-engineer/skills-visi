#!/usr/bin/env python3
"""点/线治理全库嗅探（配时 + 周期表排队口径）。

口径：
- 当前路口必须有 plan_cfg + stage_timing（可配时）
- 当前/下游均须有周期表排队（dws_inter_dir_turn_perf_5min_mm）
- 不区分单日周五；周一至周日同一晚高峰窗口合并
- 当前路口：queue_len_max / adjacent_inter_spacing_m 取 MAX
- 下游路口：同转向给出 AVG(queue_len_avg/spacing) 与 MAX(queue_len_max/spacing)
- 点治理：目标 max>=0.8 且下游 avg<0.8（披露下游 max）
- 线治理：目标 max>=0.8 且下游 avg>=0.8 或 max>=0.8
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.config import PROJECT_ROOT, get_settings
from app.data.pg_client import read_pg_rows
from app.metrics.traffic import THRESHOLDS
from app.trace.topology import exit_dir8_for_turn, movement_label

ROOT = PROJECT_ROOT
OUT_BASE = ROOT / "data" / "screening"

PM_STEP_LO, PM_STEP_HI = 204, 228
OVERFLOW_WARN = THRESHOLDS["queue_ratio_warning"]  # 0.8
SAT_HIGH = THRESHOLDS["saturation_high"]
SAT_OVERSAT = THRESHOLDS["saturation_oversaturation"]
GREEN_HIGH = THRESHOLDS["green_utilization_high"]
GREEN_LOW = THRESHOLDS["green_utilization_low"]


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


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(ser(rows))


def eight_to_dir8(eight: int) -> int:
    return int(eight) - 1


def receiving_eight_direction(exit_dir8: int) -> int:
    return ((int(exit_dir8) + 4) % 8) + 1


def load_signal_intersections() -> dict[str, dict[str, Any]]:
    rows = read_pg_rows(
        """
        SELECT p.inter_id,
               i.inter_name,
               COUNT(DISTINCT t.stage_no) AS stage_cnt,
               COUNT(DISTINCT p.plan_no) AS plan_cnt,
               MAX(p.cycle_len_sec) AS cycle_s_max
        FROM xianchang.dwd_ctl_inter_plan_cfg p
        JOIN xianchang.dwd_ctl_inter_plan_stage_timing t
          ON t.inter_id = p.inter_id AND t.plan_no = p.plan_no
         AND COALESCE(t.is_deleted, 0) = 0
        JOIN road6.dim_inter_info i
          ON i.inter_id = p.inter_id AND i.version_id = '20260501'
        WHERE COALESCE(p.is_deleted, 0) = 0
          AND COALESCE(i.is_signalized, 0) = 1
        GROUP BY p.inter_id, i.inter_name
        HAVING COUNT(DISTINCT t.stage_no) >= 2
        """,
        {},
        limit=5000,
    )
    return {str(r["inter_id"]): r for r in rows}


def load_exit_downstream() -> list[dict[str, Any]]:
    return read_pg_rows(
        """
        SELECT DISTINCT ON (w.inter_id, w.dir8_code)
               w.inter_id,
               di.inter_name AS inter_name,
               w.dir8_code::int AS exit_dir8,
               l.t_inter_id AS downstream_inter_id,
               down.inter_name AS downstream_inter_name,
               COALESCE(down.is_signalized, 0) AS downstream_signalized,
               l.lane_num AS exit_lane_num,
               l.formway AS exit_formway,
               l.length_m AS exit_link_length_m
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


def load_cycle_overflow_evening() -> list[dict[str, Any]]:
    """周期表晚高峰：不限制周五，周一至周日合并。"""
    return read_pg_rows(
        """
        WITH direction_spacing AS (
            SELECT w.inter_id,
                   (CAST(w.dir8_code AS INTEGER) + 1) AS eight_direction,
                   MIN(l.length_m) AS adjacent_inter_spacing_m,
                   MAX(l.lane_num) AS lane_num,
                   MAX(l.formway) AS formway
            FROM road6.dwd_tfc_rltn_wide_inter_ft_link w
            JOIN road6.dim_link_info l
              ON w.link_id = l.link_id AND l.version_id = w.version_id
            WHERE LOWER(w.link_role) = 'entrance'
            GROUP BY w.inter_id, w.dir8_code
            HAVING MIN(l.length_m) >= 50.0
        )
        SELECT p.inter_id,
               p.inter_name,
               p.eight_direction,
               p.turn_dir_no,
               ds.adjacent_inter_spacing_m AS storage_m,
               ds.lane_num,
               ds.formway,
               ROUND(MAX(p.queue_len_max / ds.adjacent_inter_spacing_m)::numeric, 4) AS overflow_max,
               ROUND(AVG(p.queue_len_avg / ds.adjacent_inter_spacing_m)::numeric, 4) AS overflow_avg,
               ROUND(MAX(p.queue_len_max)::numeric, 1) AS queue_max_m,
               ROUND(AVG(p.queue_len_avg)::numeric, 1) AS queue_avg_m,
               ROUND(AVG(p.pass_flow)::numeric, 1) AS pass_flow_avg,
               ROUND(AVG(p.no_stop_pass_speed)::numeric, 2) AS speed_avg,
               ROUND(MAX(p.delay_index)::numeric, 3) AS delay_index_max,
               COUNT(*)::bigint AS sample_rows,
               COUNT(DISTINCT p.day_of_week)::int AS dow_cnt
        FROM xianchang.dws_inter_dir_turn_perf_5min_mm p
        JOIN direction_spacing ds
          ON ds.inter_id = p.inter_id AND ds.eight_direction = p.eight_direction
        WHERE COALESCE(p.is_deleted, 0) = 0
          AND p.turn_dir_no IN (1, 2)
          AND p.day_of_week BETWEEN 1 AND 7
          AND p.step_index >= %(lo)s AND p.step_index < %(hi)s
          AND p.queue_len_max IS NOT NULL
        GROUP BY p.inter_id, p.inter_name, p.eight_direction, p.turn_dir_no,
                 ds.adjacent_inter_spacing_m, ds.lane_num, ds.formway
        """,
        {"lo": PM_STEP_LO, "hi": PM_STEP_HI},
        limit=200000,
    )


def load_cycle_sat_green() -> list[dict[str, Any]]:
    return read_pg_rows(
        f"""
        SELECT s.inter_id,
               (s.dir8_code + 1) AS eight_direction,
               s.turn_dir_no,
               ROUND(MAX(s.turn_saturation)::numeric, 4) AS sat_max,
               ROUND(AVG(s.turn_saturation)::numeric, 4) AS sat_avg,
               ROUND(MAX(g.green_utilization)::numeric, 4) AS green_util_max,
               ROUND(AVG(g.green_utilization)::numeric, 4) AS green_util_avg
        FROM xianchang.dws_turn_saturation_5min_mm s
        LEFT JOIN xianchang.dws_turn_green_utilization_5min_mm g
          ON g.inter_id = s.inter_id AND g.link_id = s.link_id
         AND g.turn_dir_no = s.turn_dir_no AND g.day_of_week = s.day_of_week
         AND g.step_index = s.step_index AND COALESCE(g.is_deleted, 0) = 0
        WHERE COALESCE(s.is_deleted, 0) = 0
          AND s.turn_dir_no IN (1, 2)
          AND s.day_of_week BETWEEN 1 AND 7
          AND s.step_index >= {PM_STEP_LO} AND s.step_index < {PM_STEP_HI}
        GROUP BY s.inter_id, s.dir8_code, s.turn_dir_no
        """,
        {},
        limit=200000,
    )


def load_inter_evaluation() -> dict[str, dict[str, Any]]:
    rows = read_pg_rows(
        f"""
        SELECT inter_id,
               ROUND(MAX(saturation_max)::numeric, 4) AS inter_sat_max,
               ROUND(AVG(saturation_avg)::numeric, 4) AS inter_sat_avg,
               ROUND(MAX(unbalance_index)::numeric, 4) AS unbalance_max,
               ROUND(AVG(unbalance_index)::numeric, 4) AS unbalance_avg
        FROM xianchang.dws_inter_evaluation_5min_mm
        WHERE COALESCE(is_deleted, 0) = 0
          AND day_of_week BETWEEN 1 AND 7
          AND step_index >= {PM_STEP_LO} AND step_index < {PM_STEP_HI}
        GROUP BY inter_id
        """,
        {},
        limit=10000,
    )
    return {str(r["inter_id"]): r for r in rows}


def load_channelization(inter_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not inter_ids:
        return {}
    rows = read_pg_rows(
        """
        SELECT w.inter_id,
               COUNT(*)::int AS entrance_lane_rows,
               COUNT(DISTINCT w.dir8_code)::int AS entrance_dirs,
               STRING_AGG(DISTINCT COALESCE(w.turn_move::text, ''), '|'
                          ORDER BY COALESCE(w.turn_move::text, '')) AS lane_turn_labels
        FROM road6.dwd_tfc_rltn_wide_inter_ft_lane w
        WHERE w.inter_id = ANY(%(ids)s)
          AND LOWER(COALESCE(w.link_role, 'entrance')) IN ('entrance', '')
        GROUP BY w.inter_id
        """,
        {"ids": inter_ids},
        limit=5000,
    )
    return {str(r["inter_id"]): r for r in rows}


def load_aoi_poi_nearby(inter_ids: list[str]) -> dict[str, dict[str, Any]]:
    """路口 300m 缓冲 AOI/POI 计数（有 geom_center 的路口）。"""
    if not inter_ids:
        return {}
    rows = read_pg_rows(
        """
        WITH inters AS (
            SELECT i.inter_id,
                   i.geom_center::geography AS geog
            FROM road6.dim_inter_info i
            WHERE i.version_id = '20260501'
              AND i.inter_id = ANY(%(ids)s)
              AND i.geom_center IS NOT NULL
        )
        SELECT i.inter_id,
               (SELECT COUNT(*)::int
                FROM xianchang.ods_amap_aoi_info a
                WHERE COALESCE(a.is_deleted, 0) = 0
                  AND a.geom IS NOT NULL
                  AND ST_DWithin(i.geog, a.geom::geography, 300)
               ) AS aoi_300m,
               (SELECT COUNT(*)::int
                FROM xianchang.ods_amap_poi_info p
                WHERE COALESCE(p.is_deleted, 0) = 0
                  AND p.geom IS NOT NULL
                  AND ST_DWithin(i.geog, p.geom::geography, 300)
               ) AS poi_300m
        FROM inters i
        """,
        {"ids": inter_ids},
        limit=5000,
    )
    return {str(r["inter_id"]): r for r in rows}


def classify(
    target_overflow_max: float,
    down_overflow_avg: float | None,
    down_overflow_max: float | None,
    down_sat_max: float | None = None,
) -> tuple[str, dict[str, Any]]:
    """点/线分型。

    点治理：目标 max>=0.8，下游均值 <0.8 且下游峰值 <0.8（有空间承接）。
    线治理：目标 max>=0.8，且下游也有溢流风险（均值>=0.8 或 峰值>=0.8），
             或下游饱和度峰值>=0.85（走廊受阻）。
    """
    target_risk = target_overflow_max >= OVERFLOW_WARN
    if down_overflow_avg is None and down_overflow_max is None:
        return "UNKNOWN_DOWNSTREAM", {
            "target_overflow_risk": target_risk,
            "downstream_slack_by_avg": None,
            "downstream_overflow_risk_by_avg": None,
            "downstream_overflow_risk_by_max": None,
            "downstream_sat_blocked": None,
        }

    d_avg = float(down_overflow_avg or 0.0)
    d_max = float(down_overflow_max or 0.0)
    d_sat = float(down_sat_max) if down_sat_max is not None else None
    down_slack = d_avg < OVERFLOW_WARN and d_max < OVERFLOW_WARN
    down_risk_avg = d_avg >= OVERFLOW_WARN
    down_risk_max = d_max >= OVERFLOW_WARN
    down_sat_blocked = d_sat is not None and d_sat >= THRESHOLDS["downstream_saturation_high"]
    down_risk = down_risk_avg or down_risk_max or down_sat_blocked

    if target_risk and down_slack and not down_sat_blocked:
        screen = "POINT_GOVERN"
    elif target_risk and down_risk:
        screen = "LINE_GOVERN"
    elif target_risk:
        screen = "LINE_GOVERN" if down_risk else "POINT_GOVERN"
    else:
        screen = "OTHER"

    return screen, {
        "target_overflow_risk": target_risk,
        "downstream_slack_by_avg": d_avg < OVERFLOW_WARN,
        "downstream_overflow_risk_by_avg": down_risk_avg,
        "downstream_overflow_risk_by_max": down_risk_max,
        "downstream_sat_blocked": down_sat_blocked,
    }


def metric_index(rows: list[dict[str, Any]]) -> dict[tuple[str, int, int], dict[str, Any]]:
    idx: dict[tuple[str, int, int], dict[str, Any]] = {}
    for r in rows:
        idx[(str(r["inter_id"]), int(r["eight_direction"]), int(r["turn_dir_no"]))] = r
    return idx


def build_pairs(
    overflow_rows: list[dict[str, Any]],
    sat_rows: list[dict[str, Any]],
    exit_rows: list[dict[str, Any]],
    signal_map: dict[str, dict[str, Any]],
    eval_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    ov = metric_index(overflow_rows)
    sat = metric_index(sat_rows)
    exit_map: dict[tuple[str, int], dict[str, Any]] = {}
    for r in exit_rows:
        key = (str(r["inter_id"]), int(r["exit_dir8"]))
        if key not in exit_map:
            exit_map[key] = r

    pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, str]] = set()

    for (iid, ed, td), pm in ov.items():
        if iid not in signal_map:
            continue  # 无配时过滤
        t_ov_max = float(pm.get("overflow_max") or 0)
        if t_ov_max < OVERFLOW_WARN:
            continue  # 仅保留当前有溢流风险的对

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
        recv_turn = td
        down_pm = ov.get((down_id, recv_ed, recv_turn))
        # 下游必须有排队周期表样本
        sat_m = sat.get((iid, ed, td), {})
        down_sat = sat.get((down_id, recv_ed, recv_turn), {})
        down_sat_max_val = (
            float(down_sat["sat_max"]) if down_sat and down_sat.get("sat_max") is not None else None
        )

        if not down_pm:
            screen_type, criteria = classify(t_ov_max, None, None, down_sat_max_val)
            has_down_queue = False
            d_avg = d_max = None
        else:
            has_down_queue = True
            d_avg = float(down_pm.get("overflow_avg") or 0)
            d_max = float(down_pm.get("overflow_max") or 0)
            screen_type, criteria = classify(t_ov_max, d_avg, d_max, down_sat_max_val)

        if not has_down_queue:
            continue

        sig = signal_map[iid]
        ev = eval_map.get(iid, {})
        down_ev = eval_map.get(down_id, {})

        green_max = float(sat_m.get("green_util_max") or 0) if sat_m else 0.0
        sat_max = float(sat_m.get("sat_max") or 0) if sat_m else 0.0
        empty_release_flag = bool(sat_max < SAT_HIGH and green_max > 0 and green_max < GREEN_LOW)

        pairs.append(
            {
                "screen_type": screen_type,
                "target_inter_id": iid,
                "target_inter_name": pm.get("inter_name") or sig.get("inter_name"),
                "movement": movement_label(dir8, td),
                "entrance_eight_direction": ed,
                "turn_dir_no": td,
                "exit_dir8": exit_d8,
                "downstream_inter_id": down_id,
                "downstream_inter_name": ex.get("downstream_inter_name"),
                "receiving_eight_direction": recv_ed,
                "receiving_turn_dir_no": recv_turn,
                "period": "evening_peak_17_19_cycle_all_dow",
                "target_storage_m": float(pm.get("storage_m") or 0),
                "target_overflow_max": t_ov_max,
                "target_overflow_avg": float(pm.get("overflow_avg") or 0),
                "target_queue_max_m": float(pm.get("queue_max_m") or 0),
                "target_queue_avg_m": float(pm.get("queue_avg_m") or 0),
                "target_sat_max": sat_max or None,
                "target_sat_avg": float(sat_m.get("sat_avg")) if sat_m and sat_m.get("sat_avg") is not None else None,
                "target_green_util_max": green_max or None,
                "target_green_util_avg": float(sat_m.get("green_util_avg")) if sat_m and sat_m.get("green_util_avg") is not None else None,
                "target_pass_flow_avg": float(pm.get("pass_flow_avg") or 0) if pm.get("pass_flow_avg") is not None else None,
                "target_speed_avg": float(pm.get("speed_avg") or 0) if pm.get("speed_avg") is not None else None,
                "target_delay_index_max": float(pm.get("delay_index_max") or 0) if pm.get("delay_index_max") is not None else None,
                "target_lane_num": pm.get("lane_num"),
                "target_formway": pm.get("formway"),
                "target_unbalance_max": float(ev["unbalance_max"]) if ev.get("unbalance_max") is not None else None,
                "target_inter_sat_max": float(ev["inter_sat_max"]) if ev.get("inter_sat_max") is not None else None,
                "empty_release_suspect": empty_release_flag,
                "signal_plan_cnt": int(sig.get("plan_cnt") or 0),
                "signal_stage_cnt": int(sig.get("stage_cnt") or 0),
                "signal_cycle_s_max": float(sig["cycle_s_max"]) if sig.get("cycle_s_max") is not None else None,
                "downstream_storage_m": float(down_pm.get("storage_m") or 0),
                "downstream_overflow_avg": d_avg,
                "downstream_overflow_max": d_max,
                "downstream_queue_avg_m": float(down_pm.get("queue_avg_m") or 0),
                "downstream_queue_max_m": float(down_pm.get("queue_max_m") or 0),
                "downstream_sat_max": float(down_sat["sat_max"]) if down_sat and down_sat.get("sat_max") is not None else None,
                "downstream_sat_avg": float(down_sat["sat_avg"]) if down_sat and down_sat.get("sat_avg") is not None else None,
                "downstream_green_util_max": float(down_sat["green_util_max"]) if down_sat and down_sat.get("green_util_max") is not None else None,
                "downstream_pass_flow_avg": float(down_pm.get("pass_flow_avg") or 0) if down_pm.get("pass_flow_avg") is not None else None,
                "downstream_speed_avg": float(down_pm.get("speed_avg") or 0) if down_pm.get("speed_avg") is not None else None,
                "downstream_lane_num": down_pm.get("lane_num"),
                "downstream_formway": down_pm.get("formway"),
                "downstream_unbalance_max": float(down_ev["unbalance_max"]) if down_ev.get("unbalance_max") is not None else None,
                "downstream_has_signal": down_id in signal_map,
                "exit_lane_num": ex.get("exit_lane_num"),
                "exit_formway": ex.get("exit_formway"),
                "exit_link_length_m": float(ex["exit_link_length_m"]) if ex.get("exit_link_length_m") is not None else None,
                "target_sample_rows": int(pm.get("sample_rows") or 0),
                "target_dow_cnt": int(pm.get("dow_cnt") or 0),
                "downstream_sample_rows": int(down_pm.get("sample_rows") or 0),
                "downstream_dow_cnt": int(down_pm.get("dow_cnt") or 0),
                **criteria,
            }
        )
    return pairs


def main() -> None:
    load_dotenv(ROOT / ".env", override=True)
    get_settings.cache_clear()

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = OUT_BASE / f"cycle-signal-{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("1/6 signal intersections...")
    signal_map = load_signal_intersections()
    write_json(out_dir / "signal_intersections.json", list(signal_map.values()))
    print(f"   signal={len(signal_map)}")

    print("2/6 exit->downstream topology...")
    exits = load_exit_downstream()
    write_json(out_dir / "exit_downstream.json", exits)
    print(f"   exits={len(exits)}")

    print("3/6 cycle overflow evening (all dow)...")
    ov = load_cycle_overflow_evening()
    write_json(out_dir / "cycle_overflow_evening.json", ov)
    print(f"   overflow_turns={len(ov)}")

    print("4/6 saturation + green util...")
    sat = load_cycle_sat_green()
    write_json(out_dir / "cycle_sat_green_evening.json", sat)
    print(f"   sat_turns={len(sat)}")

    print("5/6 intersection evaluation...")
    eval_map = load_inter_evaluation()
    write_json(out_dir / "inter_evaluation_evening.json", list(eval_map.values()))

    print("6/6 build pairs...")
    pairs = build_pairs(ov, sat, exits, signal_map, eval_map)

    # enrich channelization + AOI/POI for candidate targets only
    cand_ids = sorted({p["target_inter_id"] for p in pairs} | {p["downstream_inter_id"] for p in pairs})
    print(f"   enrich channelization/AOI/POI for {len(cand_ids)} intersections...")
    try:
        chan = load_channelization(cand_ids)
    except Exception as exc:  # noqa: BLE001
        print(f"   channelization skipped: {exc}")
        chan = {}
    try:
        aoi_poi = load_aoi_poi_nearby(cand_ids)
    except Exception as exc:  # noqa: BLE001
        print(f"   aoi/poi skipped: {exc}")
        aoi_poi = {}

    for p in pairs:
        c = chan.get(p["target_inter_id"], {})
        ap = aoi_poi.get(p["target_inter_id"], {})
        dap = aoi_poi.get(p["downstream_inter_id"], {})
        p["target_entrance_lane_rows"] = c.get("entrance_lane_rows")
        p["target_entrance_dirs"] = c.get("entrance_dirs")
        p["target_lane_turn_labels"] = c.get("lane_turn_labels")
        p["target_aoi_300m"] = ap.get("aoi_300m")
        p["target_poi_300m"] = ap.get("poi_300m")
        p["downstream_aoi_300m"] = dap.get("aoi_300m")
        p["downstream_poi_300m"] = dap.get("poi_300m")

    write_json(out_dir / "full_pairs.json", pairs)
    write_csv(out_dir / "full_pairs.csv", pairs)

    point = [p for p in pairs if p["screen_type"] == "POINT_GOVERN"]
    line = [p for p in pairs if p["screen_type"] == "LINE_GOVERN"]

    point.sort(key=lambda x: (-(x.get("target_overflow_max") or 0), x.get("downstream_overflow_avg") or 0))
    line.sort(key=lambda x: (-(x.get("target_overflow_max") or 0), -(x.get("downstream_overflow_max") or 0)))

    write_json(out_dir / "point_govern_candidates.json", point)
    write_csv(out_dir / "point_govern_candidates.csv", point)
    write_json(out_dir / "line_govern_candidates.json", line)
    write_csv(out_dir / "line_govern_candidates.csv", line)

    summary = {
        "generated_at": datetime.now().isoformat(),
        "output_dir": str(out_dir.relative_to(ROOT)),
        "policy": {
            "queue_source": "xianchang.dws_inter_dir_turn_perf_5min_mm",
            "day_filter": "day_of_week 1-7 (no Friday-only split)",
            "period": "evening_peak step 204-228 (17:00-19:00)",
            "target_stat": "MAX(queue_len_max / adjacent_inter_spacing_m)",
            "downstream_stat": "AVG(queue_len_avg/spacing) + MAX(queue_len_max/spacing)",
            "signal_filter": "target has plan_cfg + stage_timing (>=2 stages)",
            "queue_filter": "target and downstream both have cycle queue samples",
            "point": "target_max>=0.8 and downstream_avg<0.8 and downstream_max<0.8",
            "line": "target_max>=0.8 and (downstream_avg>=0.8 or downstream_max>=0.8 or downstream_sat_max>=0.85)",
            "overflow_warn": OVERFLOW_WARN,
        },
        "counts": {
            "signal_intersections": len(signal_map),
            "cycle_overflow_turns": len(ov),
            "corridor_pairs_with_signal_and_queue": len(pairs),
            "point_govern": len(point),
            "line_govern": len(line),
        },
        "top_point": point[:15],
        "top_line": line[:15],
    }
    write_json(out_dir / "screening_summary.json", summary)

    latest = OUT_BASE / "cycle-signal-latest"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to(out_dir.name)

    print(json.dumps(summary["counts"], ensure_ascii=False, indent=2))
    print(f"Done: {out_dir}")


if __name__ == "__main__":
    main()
