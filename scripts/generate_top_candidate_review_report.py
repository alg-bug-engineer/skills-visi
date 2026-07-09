#!/usr/bin/env python3
"""Top 候选路口详细指标报告（人工复核用）。

口径对齐 scripts/screen_point_line_intersections.py 与 analysis/溢流路口统计优化.sql。
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.data.pg_client import read_pg_rows
from app.metrics.traffic import THRESHOLDS
from app.trace.topology import DIR8_ENTRY, TURN_LABEL

ROOT = Path(__file__).resolve().parents[1]
SCREENING_DIR = ROOT / "data" / "screening" / "point-line-latest"
OUT_BASE = ROOT / "data" / "screening"

PERIODS = {
    "morning_peak": {"label": "早高峰 07-09", "step_lo": 84, "step_hi": 108, "time_sql": "AND d.stat_time::time >= '07:00' AND d.stat_time::time < '09:00'"},
    "midday": {"label": "白平峰 10-16", "step_lo": 120, "step_hi": 192, "time_sql": "AND d.stat_time::time >= '10:00' AND d.stat_time::time < '16:00'"},
    "evening_peak": {"label": "晚高峰 17-19", "step_lo": 204, "step_hi": 228, "time_sql": "AND d.stat_time::time >= '17:00' AND d.stat_time::time < '19:00'"},
    "all_day": {"label": "全天", "step_lo": 0, "step_hi": 288, "time_sql": ""},
}

TOP_CANDIDATES = [
    {
        "rank": 1,
        "inter_id": "011wwe0rtv700001",
        "alias": "燕子山西路×环山路",
        "screen_type": "TYPE1_POINT",
        "reason": "东进口直行→环山路，晚高峰溢流比 max=2.76，下游有承接空间",
    },
    {
        "rank": 2,
        "inter_id": "011wwe28fty00001",
        "alias": "坤顺路×奥体西路",
        "screen_type": "TYPE1_POINT",
        "reason": "多转向饱和≥0.9、下游余量大，典型点优化候选",
    },
    {
        "rank": 3,
        "inter_id": "011wwe0rynv00001",
        "alias": "二环东路×浆水泉西路",
        "screen_type": "TYPE2_LINE",
        "reason": "北进口直行→二环东路辅路，目标饱和 0.94、下游饱和 2.12",
    },
    {
        "rank": 4,
        "inter_id": "011wwe22jsg00001",
        "alias": "旅游路×荆山东路",
        "screen_type": "TYPE2_LINE",
        "reason": "西进口直行↔旅游路×浆水泉路双向线优化走廊",
        "related_inter_id": "011wwe22mcj00001",
        "related_name": "旅游路与浆水泉路路口",
    },
    {
        "rank": 5,
        "inter_id": "011wwe294k300001",
        "alias": "解放东路×奥体中路",
        "screen_type": "TYPE2_LINE",
        "reason": "南进口直行→坤顺路×奥体中路，目标/下游均过饱和",
    },
]

DIRECTION_SPACING_CTE = """
direction_spacing AS (
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
"""


def ser(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: ser(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [ser(x) for x in obj]
    return obj


def fmt(v: Any, digits: int = 4) -> str:
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        return f"{v:.{digits}f}" if digits else str(v)
    return str(v)


def dir_label(eight_direction: int) -> str:
    return DIR8_ENTRY.get(int(eight_direction) - 1, f"dir({eight_direction})")


def turn_label(turn_dir_no: int) -> str:
    return TURN_LABEL.get(int(turn_dir_no), str(turn_dir_no))


def load_basic(inter_id: str) -> dict[str, Any]:
    rows = read_pg_rows(
        """
        SELECT inter_id, inter_name, is_signalized, inter_type, inter_proto,
               entr_cnt, entr_dir8, version_id
        FROM road6.dim_inter_info
        WHERE inter_id = %(iid)s AND version_id = '20260501'
        LIMIT 1
        """,
        {"iid": inter_id},
        limit=1,
    )
    return rows[0] if rows else {"inter_id": inter_id}


def load_spacing(inter_id: str) -> list[dict[str, Any]]:
    return read_pg_rows(
        f"""
        WITH {DIRECTION_SPACING_CTE}
        SELECT ds.eight_direction, ds.adjacent_inter_spacing_m
        FROM direction_spacing ds
        WHERE ds.inter_id = %(iid)s
        ORDER BY ds.eight_direction
        """,
        {"iid": inter_id},
        limit=20,
    )


def load_overflow_period(inter_id: str, period_key: str) -> dict[str, Any]:
    p = PERIODS[period_key]
    rows = read_pg_rows(
        f"""
        WITH {DIRECTION_SPACING_CTE}
        SELECT
            ROUND(MAX(d.queue_len_avg)::numeric, 1) AS queue_max_m,
            ROUND(AVG(d.queue_len_avg)::numeric, 2) AS queue_mean_m,
            ROUND(AVG(ds.adjacent_inter_spacing_m)::numeric, 2) AS spacing_mean_m,
            ROUND(MAX(d.queue_len_avg / ds.adjacent_inter_spacing_m)::numeric, 4) AS overflow_max,
            ROUND(AVG(d.queue_len_avg / ds.adjacent_inter_spacing_m)::numeric, 4) AS overflow_mean,
            COUNT(*)::bigint AS sample_rows
        FROM xianchang.dwd_tfc_inter_dir_perf_5min d
        JOIN direction_spacing ds
          ON d.inter_id = ds.inter_id AND d.eight_direction = ds.eight_direction
        WHERE d.inter_id = %(iid)s
          AND d.is_deleted = 0
          AND d.turn_dir_no IN (1, 2)
          {p['time_sql']}
        """,
        {"iid": inter_id},
        limit=1,
    )
    return rows[0] if rows else {}


def load_turn_overflow_top(inter_id: str, period_key: str, limit: int = 8) -> list[dict[str, Any]]:
    p = PERIODS[period_key]
    return read_pg_rows(
        f"""
        WITH {DIRECTION_SPACING_CTE}
        SELECT d.eight_direction,
               d.turn_dir_no,
               ds.adjacent_inter_spacing_m AS spacing_m,
               ROUND(MAX(d.queue_len_avg)::numeric, 1) AS queue_max_m,
               ROUND(MAX(d.queue_len_avg / ds.adjacent_inter_spacing_m)::numeric, 4) AS overflow_max,
               ROUND(AVG(d.queue_len_avg / ds.adjacent_inter_spacing_m)::numeric, 4) AS overflow_mean,
               COUNT(*)::bigint AS sample_rows
        FROM xianchang.dwd_tfc_inter_dir_perf_5min d
        JOIN direction_spacing ds
          ON d.inter_id = ds.inter_id AND d.eight_direction = ds.eight_direction
        WHERE d.inter_id = %(iid)s
          AND d.is_deleted = 0
          AND d.turn_dir_no IN (1, 2)
          {p['time_sql']}
        GROUP BY d.eight_direction, d.turn_dir_no, ds.adjacent_inter_spacing_m
        ORDER BY overflow_max DESC NULLS LAST
        LIMIT %(lim)s
        """,
        {"iid": inter_id, "lim": limit},
        limit=limit,
    )


def load_dws_period(inter_id: str, period_key: str) -> dict[str, Any]:
    p = PERIODS[period_key]
    sat = read_pg_rows(
        f"""
        SELECT ROUND(MAX(s.turn_saturation)::numeric, 4) AS turn_sat_max,
               ROUND(AVG(s.turn_saturation)::numeric, 4) AS turn_sat_mean
        FROM xianchang.dws_turn_saturation_5min_mm s
        WHERE s.inter_id = %(iid)s AND s.is_deleted = 0
          AND s.day_of_week BETWEEN 1 AND 7
          AND s.step_index >= %(lo)s AND s.step_index < %(hi)s
        """,
        {"iid": inter_id, "lo": p["step_lo"], "hi": p["step_hi"]},
        limit=1,
    )
    inter = read_pg_rows(
        f"""
        SELECT ROUND(MAX(e.saturation_max)::numeric, 4) AS inter_sat_max,
               ROUND(AVG(e.saturation_max)::numeric, 4) AS inter_sat_mean,
               ROUND(MAX(e.unbalance_index)::numeric, 4) AS unbalance_max,
               ROUND(AVG(e.unbalance_index)::numeric, 4) AS unbalance_mean
        FROM xianchang.dws_inter_evaluation_5min_mm e
        WHERE e.inter_id = %(iid)s AND e.is_deleted = 0
          AND e.day_of_week BETWEEN 1 AND 7
          AND e.step_index >= %(lo)s AND e.step_index < %(hi)s
        """,
        {"iid": inter_id, "lo": p["step_lo"], "hi": p["step_hi"]},
        limit=1,
    )
    green = read_pg_rows(
        f"""
        SELECT ROUND(MAX(g.green_utilization)::numeric, 4) AS green_util_max,
               ROUND(AVG(g.green_utilization)::numeric, 4) AS green_util_mean
        FROM xianchang.dws_turn_green_utilization_5min_mm g
        WHERE g.inter_id = %(iid)s AND g.is_deleted = 0
          AND g.day_of_week BETWEEN 1 AND 7
          AND g.step_index >= %(lo)s AND g.step_index < %(hi)s
        """,
        {"iid": inter_id, "lo": p["step_lo"], "hi": p["step_hi"]},
        limit=1,
    )
    turn_top = read_pg_rows(
        f"""
        SELECT (s.dir8_code + 1) AS eight_direction,
               s.turn_dir_no,
               ROUND(MAX(s.turn_saturation)::numeric, 4) AS sat_max,
               ROUND(AVG(s.turn_saturation)::numeric, 4) AS sat_mean
        FROM xianchang.dws_turn_saturation_5min_mm s
        WHERE s.inter_id = %(iid)s AND s.is_deleted = 0
          AND s.turn_dir_no IN (1, 2)
          AND s.day_of_week BETWEEN 1 AND 7
          AND s.step_index >= %(lo)s AND s.step_index < %(hi)s
        GROUP BY s.dir8_code, s.turn_dir_no
        ORDER BY sat_max DESC NULLS LAST
        LIMIT 8
        """,
        {"iid": inter_id, "lo": p["step_lo"], "hi": p["step_hi"]},
        limit=8,
    )
    out: dict[str, Any] = {}
    if sat:
        out.update(sat[0])
    if inter:
        out.update(inter[0])
    if green:
        out.update(green[0])
    out["turn_sat_top"] = turn_top
    return out


def load_table_coverage(inter_id: str) -> dict[str, int]:
    tables = [
        ("turn_saturation", "xianchang.dws_turn_saturation_5min_mm"),
        ("inter_evaluation", "xianchang.dws_inter_evaluation_5min_mm"),
        ("green_utilization", "xianchang.dws_turn_green_utilization_5min_mm"),
        ("dwd_perf", "xianchang.dwd_tfc_inter_dir_perf_5min"),
        ("turn_flow", "xianchang.dws_inter_link_turn_flow_5min_mm"),
        ("plan_cfg", "xianchang.dwd_ctl_inter_plan_cfg"),
    ]
    counts: dict[str, int] = {}
    for key, table in tables:
        try:
            rows = read_pg_rows(
                f"SELECT COUNT(*)::bigint AS cnt FROM {table} WHERE inter_id = %(iid)s",
                {"iid": inter_id},
                limit=1,
            )
            counts[key] = int(rows[0]["cnt"]) if rows else 0
        except Exception:
            counts[key] = -1
    return counts


def load_signal_summary(inter_id: str) -> list[dict[str, Any]]:
    return read_pg_rows(
        """
        SELECT p.plan_no,
               p.cycle_len_sec AS cycle_s,
               p.offset_sec AS offset_s,
               p.coord_stage_no,
               COUNT(DISTINCT t.stage_no) AS stage_count,
               SUM(t.green_sec)::int AS total_green_s
        FROM xianchang.dwd_ctl_inter_plan_cfg p
        LEFT JOIN xianchang.dwd_ctl_inter_plan_stage_timing t
          ON t.inter_id = p.inter_id AND t.plan_no = p.plan_no AND t.is_deleted = 0
        WHERE p.inter_id = %(iid)s AND p.is_deleted = 0
        GROUP BY p.plan_no, p.cycle_len_sec, p.offset_sec, p.coord_stage_no
        ORDER BY p.plan_no
        LIMIT 12
        """,
        {"iid": inter_id},
        limit=12,
    )


def load_corridor_pairs(inter_id: str, pairs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    as_target = [p for p in pairs if p.get("target_inter_id") == inter_id]
    as_downstream = [p for p in pairs if p.get("downstream_inter_id") == inter_id]
    as_target.sort(key=lambda x: (-(x.get("target_overflow_max_pm") or 0), -(x.get("target_sat_max_pm") or 0)))
    as_downstream.sort(key=lambda x: -(x.get("downstream_sat_max_pm") or 0))
    return {"as_target": as_target, "as_downstream": as_downstream}


def build_intersection_report(inter_id: str, meta: dict[str, Any], pairs: list[dict[str, Any]]) -> dict[str, Any]:
    basic = load_basic(inter_id)
    spacing = load_spacing(inter_id)
    coverage = load_table_coverage(inter_id)
    signal = load_signal_summary(inter_id)
    corridors = load_corridor_pairs(inter_id, pairs)

    period_overflow: dict[str, Any] = {}
    period_dws: dict[str, Any] = {}
    turn_overflow_evening: list[dict[str, Any]] = []
    for pk in PERIODS:
        period_overflow[pk] = load_overflow_period(inter_id, pk)
        period_dws[pk] = load_dws_period(inter_id, pk)
    turn_overflow_evening = load_turn_overflow_top(inter_id, "evening_peak")
    turn_overflow_all = load_turn_overflow_top(inter_id, "all_day")

    flags: list[str] = []
    if coverage.get("dwd_perf", 0) == 0:
        flags.append("无 DWD 排队/溢流时序，溢流比不可信")
    if coverage.get("turn_saturation", 0) == 0:
        flags.append("无 DWS 转向饱和度")
    strong_corridors = [c for c in corridors["as_target"] if c.get("screen_type") in ("TYPE1_POINT", "TYPE2_LINE")]
    if not strong_corridors:
        flags.append("本路口在筛选中无严格 Type1/Type2 走廊（复核时注意弱分型）")

    return {
        **meta,
        "inter_id": inter_id,
        "inter_name": basic.get("inter_name"),
        "basic": basic,
        "approach_spacing": spacing,
        "table_coverage": coverage,
        "period_overflow": period_overflow,
        "period_dws": period_dws,
        "turn_overflow_evening_top": turn_overflow_evening,
        "turn_overflow_all_top": turn_overflow_all,
        "signal_plans": signal,
        "corridors": corridors,
        "data_flags": flags,
        "manual_review": {
            "screening_type_confirmed": None,
            "overflow_threshold_credible": None,
            "downstream_assessment_ok": None,
            "recommended_action": None,
            "reviewer_notes": "",
        },
    }


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_（无数据）_\n"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def render_corridor_table(corridors: list[dict[str, Any]], role: str) -> str:
    if not corridors:
        return "_（无）_\n"
    rows = []
    for c in corridors[:10]:
        if role == "target":
            rows.append(
                [
                    c.get("movement", "—"),
                    c.get("downstream_inter_name", "—"),
                    c.get("screen_type", "—"),
                    fmt(c.get("target_overflow_max_pm")),
                    fmt(c.get("target_sat_max_pm")),
                    fmt(c.get("downstream_overflow_max_pm")),
                    fmt(c.get("downstream_sat_max_pm")),
                ]
            )
        else:
            rows.append(
                [
                    c.get("target_inter_name", "—"),
                    c.get("movement", "—"),
                    c.get("screen_type", "—"),
                    fmt(c.get("target_overflow_max_pm")),
                    fmt(c.get("target_sat_max_pm")),
                    fmt(c.get("downstream_overflow_max_pm")),
                    fmt(c.get("downstream_sat_max_pm")),
                ]
            )
    headers = (
        ["转向", "下游路口", "分型", "目标溢流max", "目标饱和max", "下游溢流max", "下游饱和max"]
        if role == "target"
        else ["上游路口", "上游转向", "分型", "目标溢流max", "目标饱和max", "下游溢流max", "下游饱和max"]
    )
    return md_table(headers, rows)


def render_markdown(reports: list[dict[str, Any]], generated_at: str) -> str:
    parts = [
        "# Top5 候选路口详细指标报告（人工复核）",
        "",
        f"> 生成时间：{generated_at}",
        "> 溢流比口径：`queue_len_avg / direction_spacing.adjacent_inter_spacing_m`（对齐 `analysis/溢流路口统计优化.sql`）",
        f"> 阈值：溢流预警 {THRESHOLDS['queue_ratio_warning']} / 溢流 {THRESHOLDS['queue_ratio_spillback']} / 饱和高 {THRESHOLDS['saturation_high']} / 过饱和 {THRESHOLDS['saturation_oversaturation']}",
        "",
        "## 候选索引",
        "",
        md_table(
            ["#", "别名", "inter_id", "库内名称", "筛选分型", "入选理由"],
            [
                [
                    str(r["rank"]),
                    r.get("alias", "—"),
                    r["inter_id"],
                    r.get("inter_name") or "—",
                    r.get("screen_type", "—"),
                    r.get("reason", "—"),
                ]
                for r in reports
            ],
        ),
    ]

    for r in reports:
        parts += [
            "---",
            "",
            f"## #{r['rank']} {r.get('alias')} — {r.get('inter_name')} (`{r['inter_id']}`)",
            "",
            f"**筛选分型**：{r.get('screen_type')} | **入选理由**：{r.get('reason')}",
        ]
        if r.get("related_inter_id"):
            parts.append(f"**关联走廊路口**：{r.get('related_name')} (`{r['related_inter_id']}`)")
        if r.get("data_flags"):
            parts.append(f"**数据警示**：{'；'.join(r['data_flags'])}")
        parts.append("")

        parts += ["### 1. 静态与数据覆盖", ""]
        b = r.get("basic") or {}
        parts.append(
            md_table(
                ["字段", "值"],
                [
                    ["is_signalized", str(b.get("is_signalized"))],
                    ["inter_type", str(b.get("inter_type"))],
                    ["entr_cnt", str(b.get("entr_cnt"))],
                ],
            )
        )
        cov = r.get("table_coverage") or {}
        parts.append(
            md_table(
                ["表", "行数"],
                [[k, str(v)] for k, v in cov.items()],
            )
        )

        parts += ["### 2. 进口道间距 (direction_spacing)", ""]
        parts.append(
            md_table(
                ["进口方向", "eight_direction", "间距m"],
                [
                    [dir_label(row["eight_direction"]), str(row["eight_direction"]), fmt(row["adjacent_inter_spacing_m"], 2)]
                    for row in r.get("approach_spacing") or []
                ],
            )
        )

        parts += ["### 3. 排队/溢流（路口级，DWD×间距）", ""]
        rows = []
        for pk, label in [(k, PERIODS[k]["label"]) for k in PERIODS]:
            po = (r.get("period_overflow") or {}).get(pk) or {}
            rows.append(
                [
                    label,
                    fmt(po.get("queue_max_m"), 1),
                    fmt(po.get("queue_mean_m"), 2),
                    fmt(po.get("spacing_mean_m"), 2),
                    fmt(po.get("overflow_max")),
                    fmt(po.get("overflow_mean")),
                    str(po.get("sample_rows") or "—"),
                ]
            )
        parts.append(
            md_table(
                ["时段", "排队峰值m", "排队均值m", "间距均值m", "溢流比峰值", "溢流比均值", "样本行"],
                rows,
            )
        )

        parts += ["### 4. 态势指标（DWS 5min 周内典型日）", ""]
        dws_rows = []
        for pk, label in [(k, PERIODS[k]["label"]) for k in PERIODS]:
            d = (r.get("period_dws") or {}).get(pk) or {}
            dws_rows.append(
                [
                    label,
                    fmt(d.get("turn_sat_max")),
                    fmt(d.get("inter_sat_max")),
                    fmt(d.get("unbalance_max")),
                    fmt(d.get("green_util_max")),
                    fmt(d.get("turn_sat_mean")),
                    fmt(d.get("inter_sat_mean")),
                ]
            )
        parts.append(
            md_table(
                ["时段", "转向饱和max", "路口饱和max", "失衡max", "绿灯利用max", "转向饱和mean", "路口饱和mean"],
                dws_rows,
            )
        )

        parts += ["#### 晚高峰转向饱和 Top", ""]
        evening = (r.get("period_dws") or {}).get("evening_peak") or {}
        parts.append(
            md_table(
                ["方向", "转向", "饱和max", "饱和mean"],
                [
                    [dir_label(t["eight_direction"]), turn_label(t["turn_dir_no"]), fmt(t.get("sat_max")), fmt(t.get("sat_mean"))]
                    for t in evening.get("turn_sat_top") or []
                ],
            )
        )

        parts += ["### 5. 转向级溢流 Top（晚高峰 / 全天）", ""]
        for title, key in [("晚高峰", "turn_overflow_evening_top"), ("全天", "turn_overflow_all_top")]:
            parts.append(f"#### {title}")
            parts.append(
                md_table(
                    ["方向", "转向", "间距m", "排队峰值m", "溢流比max", "溢流比mean", "样本行"],
                    [
                        [
                            dir_label(t["eight_direction"]),
                            turn_label(t["turn_dir_no"]),
                            fmt(t.get("spacing_m"), 2),
                            fmt(t.get("queue_max_m"), 1),
                            fmt(t.get("overflow_max")),
                            fmt(t.get("overflow_mean")),
                            str(t.get("sample_rows") or "—"),
                        ]
                        for t in r.get(key) or []
                    ],
                )
            )

        parts += ["### 6. 走廊配对（全库筛选结果）", ""]
        parts.append("#### 作为目标路口（出流走廊）")
        parts.append(render_corridor_table((r.get("corridors") or {}).get("as_target") or [], "target"))
        parts.append("#### 作为下游路口（入流承接）")
        parts.append(render_corridor_table((r.get("corridors") or {}).get("as_downstream") or [], "downstream"))

        parts += ["### 7. 配时方案摘要（前 12 套）", ""]
        parts.append(
            md_table(
                ["plan_no", "cycle_s", "offset_s", "coord_stage", "stages", "total_green_s"],
                [
                    [
                        str(p.get("plan_no")),
                        str(p.get("cycle_s")),
                        str(p.get("offset_s")),
                        str(p.get("coord_stage_no")),
                        str(p.get("stage_count")),
                        str(p.get("total_green_s")),
                    ]
                    for p in r.get("signal_plans") or []
                ],
            )
        )

        parts += [
            "### 8. 人工复核清单",
            "",
            "| 检查项 | 结论（待填：是/否/待定） | 备注 |",
            "| --- | --- | --- |",
            "| 筛选分型与现场一致 |  |  |",
            "| 溢流比峰值可信（间距口径 + DWD 有样本） |  |  |",
            "| 下游承接判断正确 |  |  |",
            "| 建议优化类型（点/线/暂不） |  |  |",
            "| 需补数或排除原因 |  |  |",
            "",
        ]

    return "\n".join(parts)


def main() -> None:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = OUT_BASE / f"top5-review-{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().isoformat()

    pairs_path = SCREENING_DIR / "full_pair_screening_results.json"
    pairs = json.loads(pairs_path.read_text(encoding="utf-8")) if pairs_path.exists() else []

    reports: list[dict[str, Any]] = []
    for cand in TOP_CANDIDATES:
        print(f"Loading #{cand['rank']} {cand['alias']}...")
        report = build_intersection_report(cand["inter_id"], cand, pairs)
        reports.append(report)
        write_path = out_dir / f"{cand['rank']:02d}_{cand['inter_id']}.json"
        write_path.write_text(json.dumps(ser(report), ensure_ascii=False, indent=2), encoding="utf-8")

    payload = {
        "generated_at": generated_at,
        "screening_ref": str(SCREENING_DIR.relative_to(ROOT)),
        "thresholds": THRESHOLDS,
        "candidates": reports,
    }
    (out_dir / "top5_review_bundle.json").write_text(
        json.dumps(ser(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = render_markdown(reports, generated_at)
    (out_dir / "top5_review_report.md").write_text(md, encoding="utf-8")
    (out_dir / "README.md").write_text(
        f"""# Top5 候选路口人工复核包

生成时间：{generated_at}

| 文件 | 说明 |
|------|------|
| `top5_review_report.md` | 汇总可读报告（含人工复核表） |
| `top5_review_bundle.json` | 五路口完整 JSON |
| `01_*.json` … `05_*.json` | 分路口明细 |

筛选来源：`{SCREENING_DIR.relative_to(ROOT)}`
""",
        encoding="utf-8",
    )

    latest = OUT_BASE / "top5-review-latest"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to(out_dir.name)

    print(f"Done. Output: {out_dir}")


if __name__ == "__main__":
    main()
