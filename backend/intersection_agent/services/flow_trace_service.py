"""Flow source tracing for problem turns (upstream 1-hop coverage).

接入「问题诊断环节」：对过饱和/问题转向，分析上游来源结构，把"需求调控/上游控流"
从口号具体到「哪个上游路口、哪个方位贡献了多少途经车流」。

数据：xianchang.dws_tfc_inter_turn_flow_correlate_m（月度、转向级、UPSTREAM）。
关键语义：flow_share_ratio = 本进口某转向车流中"途经过"该上游转向的比例（多跳叠加，
可 >100%）。同一上游方位随距离单调衰减——一跳 = 同方位 coverage 最大者。
"""

from __future__ import annotations

import logging
from typing import Any

from intersection_agent.db.postgres import PostgresPool
from intersection_agent.config import Settings, get_settings
from intersection_agent.models.domain import NluResult
from intersection_agent.utils.thresholds_loader import threshold_value

logger = logging.getLogger(__name__)

_DIR8_ENTRY = {
    0: "北进口", 1: "东北进口", 2: "东进口", 3: "东南进口",
    4: "南进口", 5: "西南进口", 6: "西进口", 7: "西北进口",
}
# flow_correlate / dws_turn_saturation 转向编码：1左 2直 3右 4掉头
_TURN = {1: "左转", 2: "直行", 3: "右转", 4: "掉头"}

_PERIOD_BY_LABEL = {
    "早高峰": "MORNING_PEAK",
    "晚高峰": "EVENING_PEAK",
    "平峰": "OFF_PEAK",
}


def movement_label(dir8: int | None, turn: int | None) -> str:
    """e.g. (0,2) -> 北进口直行。"""
    entry = _DIR8_ENTRY.get(int(dir8) if dir8 is not None else -1, "")
    turn_cn = _TURN.get(int(turn) if turn is not None else -1, "")
    return f"{entry}{turn_cn}" if entry and turn_cn else (entry or turn_cn or "")


def period_type_from_label(label: str | None) -> str:
    """NLU 时段 label → period_type；未知归 OFF_PEAK。"""
    for key, value in _PERIOD_BY_LABEL.items():
        if label and key in label:
            return value
    return "OFF_PEAK"


def day_labels_for_filter(dow_filter: tuple[int, ...]) -> list[str]:
    """dow_filter → flow_correlate day_of_week 可接受标签（含聚合与逐日）。"""
    if set(dow_filter) <= {6, 7}:
        return ["非工作日", "周六", "周日"]
    return ["工作日", "周一", "周二", "周三", "周四", "周五"]


def lock_one_hop(rows: list[dict[str, Any]]) -> dict[tuple[int, int], list[dict[str, Any]]]:
    """按 (本进口 dir8, 本转向) 分组；每个上游方位仅保留 coverage 最大者（一跳）。

    返回 {(f_dir8, turn): [一跳来源, ...]}，组内按 coverage 降序。
    """
    # 先按 (my_dir8, my_turn, cor_dir8, cor_turn) 取最大 coverage
    best: dict[tuple[int, int, int, int], dict[str, Any]] = {}
    for r in rows:
        try:
            key = (
                int(r["f_dir8_no"]), int(r["turn_dir_no"]),
                int(r["cor_f_dir8_no"]), int(r["cor_turn_dir_no"]),
            )
        except (TypeError, ValueError, KeyError):
            continue
        cov = _as_float(r.get("flow_share_ratio"))
        if cov is None:
            continue
        prev = best.get(key)
        if prev is None or cov > prev["coverage"]:
            best[key] = {
                "cor_inter_id": str(r.get("cor_inter_id") or ""),
                "cor_inter_name": str(r.get("cor_inter_name") or "") or None,
                "cor_dir8": key[2],
                "cor_turn": key[3],
                "coverage": cov,
                "lng": _as_float(r.get("cor_lng")),
                "lat": _as_float(r.get("cor_lat")),
            }
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for (my_dir8, my_turn, _cd, _ct), node in best.items():
        grouped.setdefault((my_dir8, my_turn), []).append(node)
    for nodes in grouped.values():
        nodes.sort(key=lambda n: n["coverage"], reverse=True)
    return grouped


def one_hop_for_approach(
    rows: list[dict[str, Any]], dir8: int
) -> dict[str, Any] | None:
    """对指定进口道，返回 coverage 最大的一跳上游节点（含 feeding_dir8）。"""
    grouped = lock_one_hop(rows)
    candidates: list[dict[str, Any]] = []
    for (d8, _turn), nodes in grouped.items():
        if d8 == dir8:
            candidates.extend(nodes)
    if not candidates:
        return None
    best = max(candidates, key=lambda n: n["coverage"])
    return {
        "cor_inter_id": best["cor_inter_id"],
        "cor_inter_name": best.get("cor_inter_name"),
        "feeding_dir8": best["cor_dir8"],
        "coverage": best["coverage"],
        "lng": best.get("lng"),
        "lat": best.get("lat"),
    }


def classify_sources(
    nodes: list[dict[str, Any]],
    *,
    coverage_high: float,
    gap_significant: float,
) -> str:
    """来源结构判定：single_corridor / multi_corridor / local。"""
    if not nodes:
        return "local"
    strong = [n for n in nodes if n["coverage"] >= coverage_high]
    if not strong:
        return "local"
    if len(strong) >= 2:
        top1, top2 = nodes[0]["coverage"], nodes[1]["coverage"]
        if top1 - top2 >= gap_significant:
            return "single_corridor"
        return "multi_corridor"
    return "single_corridor"


def build_entry_traces(
    grouped: dict[tuple[int, int], list[dict[str, Any]]],
    entry_dir8_list: list[int],
    by_turn: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按进口道聚合：一跳上一路口 + 上游左/直/右归一化为 100 辆车模型。"""
    entry_sat: dict[int, float] = {}
    for row in by_turn:
        d8 = row.get("dir8_code")
        if d8 is None:
            continue
        sat = _as_float(row.get("turn_saturation")) or 0.0
        entry_sat[int(d8)] = max(entry_sat.get(int(d8), 0.0), sat)

    out: list[dict[str, Any]] = []
    for dir8 in entry_dir8_list:
        nodes: list[dict[str, Any]] = []
        for (d8, _turn), nlist in grouped.items():
            if d8 != dir8:
                continue
            nodes.extend(nlist)
        if not nodes:
            continue

        by_inter: dict[str, list[dict[str, Any]]] = {}
        for n in nodes:
            by_inter.setdefault(str(n["cor_inter_id"]), []).append(n)
        up_id = max(by_inter, key=lambda i: max(x["coverage"] for x in by_inter[i]))
        up_nodes = by_inter[up_id]
        up_name = next(
            (n.get("cor_inter_name") for n in up_nodes if n.get("cor_inter_name")),
            "上一路口",
        )
        up_lng = next((n.get("lng") for n in up_nodes if n.get("lng") is not None), None)
        up_lat = next((n.get("lat") for n in up_nodes if n.get("lat") is not None), None)

        by_up_turn: dict[int, dict[str, Any]] = {}
        for n in up_nodes:
            t = int(n["cor_turn"])
            if t not in by_up_turn or n["coverage"] > by_up_turn[t]["coverage"]:
                by_up_turn[t] = n

        total = sum(n["coverage"] for n in by_up_turn.values()) or 1.0
        movements: list[dict[str, Any]] = []
        for t, n in sorted(by_up_turn.items(), key=lambda x: -x[1]["coverage"]):
            share = round(n["coverage"] / total * 100, 1)
            vehicles = int(round(share))
            movements.append(
                {
                    "turn": _TURN.get(t, str(t)),
                    "cor_turn": t,
                    "feed_direction": movement_label(n["cor_dir8"], t),
                    "share_pct": share,
                    "vehicles_of_100": vehicles,
                    "raw_coverage": round(n["coverage"], 1),
                }
            )

        dom = movements[0] if movements else None
        entry_label = _DIR8_ENTRY.get(dir8, "")
        if dom:
            narrative = (
                f"{entry_label}约100辆过境车中，约{dom['vehicles_of_100']}辆来自上一路口"
                f"{up_name}，以{dom['turn']}为主（{dom['vehicles_of_100']}辆）"
            )
        else:
            narrative = f"{entry_label}暂无可用上一跳溯源"

        out.append(
            {
                "entry": entry_label,
                "dir8_code": dir8,
                "entry_max_saturation": entry_sat.get(dir8),
                "upstream_inter_id": up_id,
                "upstream_inter_name": up_name,
                "upstream_lng": up_lng,
                "upstream_lat": up_lat,
                "vehicles_base": 100,
                "upstream_movements": movements,
                "dominant_movement": dom,
                "narrative": narrative,
            }
        )
    return out


def select_problem_entries(
    by_turn: list[dict[str, Any]],
    *,
    trigger_saturation: float,
) -> list[int]:
    """问题进口道 = 该进口道上任一转向饱和度 ≥ 阈值。"""
    by_dir8: dict[int, float] = {}
    for row in by_turn:
        d8 = row.get("dir8_code")
        if d8 is None:
            continue
        sat = _as_float(row.get("turn_saturation"))
        if sat is None:
            continue
        by_dir8[int(d8)] = max(by_dir8.get(int(d8), 0.0), sat)
    return sorted(d8 for d8, sat in by_dir8.items() if sat >= trigger_saturation)


def governance_hints_from_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从进口道溯源提炼治理 hint（主导上游转向 ≥50 辆/100）。"""
    hints: list[dict[str, Any]] = []
    for entry in entries:
        dom = entry.get("dominant_movement")
        if not dom or int(dom.get("vehicles_of_100") or 0) < 50:
            continue
        hints.append(
            {
                "type": "upstream_coordination",
                "problem_turn": entry.get("entry"),
                "inter_id": entry.get("upstream_inter_id"),
                "inter_name": entry.get("upstream_inter_name"),
                "feed_direction": dom.get("feed_direction"),
                "coverage": dom.get("vehicles_of_100"),
            }
        )
    return hints


def build_problem_turn_trace(
    grouped: dict[tuple[int, int], list[dict[str, Any]]],
    problem_turns: list[dict[str, Any]],
    *,
    coverage_high: float,
    gap_significant: float,
    top_sources: int,
) -> list[dict[str, Any]]:
    """对每个问题转向，组装来源结构与治理 hint。"""
    out: list[dict[str, Any]] = []
    for pt in problem_turns:
        dir8 = pt.get("dir8_code")
        turn = pt.get("turn_dir_no")
        if dir8 is None or turn is None:
            continue
        nodes = grouped.get((int(dir8), int(turn))) or []
        if not nodes:
            continue
        pattern = classify_sources(
            nodes, coverage_high=coverage_high, gap_significant=gap_significant
        )
        top = nodes[:top_sources]
        sources = [
            {
                "inter_id": n["cor_inter_id"],
                "inter_name": n["cor_inter_name"],
                "feed_direction": movement_label(n["cor_dir8"], n["cor_turn"]),
                "path_coverage": round(n["coverage"], 1),
                "lng": n.get("lng"),
                "lat": n.get("lat"),
            }
            for n in top
        ]
        dominant = sources[0] if sources else None
        out.append(
            {
                "entry": _DIR8_ENTRY.get(int(dir8), ""),
                "turn": _TURN.get(int(turn), ""),
                "turn_saturation": pt.get("turn_saturation"),
                "source_pattern": pattern,
                "dominant_feed": dominant if pattern != "local" else None,
                "sources": sources,
            }
        )
    return out


def governance_hints_from_trace(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从问题转向溯源结果提炼治理 hint，供 action_plan 消费。"""
    hints: list[dict[str, Any]] = []
    for t in turns:
        pattern = t.get("source_pattern")
        dom = t.get("dominant_feed")
        if pattern == "single_corridor" and dom:
            hints.append(
                {
                    "type": "upstream_coordination",
                    "problem_turn": f"{t.get('entry')}{t.get('turn')}",
                    "inter_id": dom.get("inter_id"),
                    "inter_name": dom.get("inter_name"),
                    "feed_direction": dom.get("feed_direction"),
                    "coverage": dom.get("path_coverage"),
                }
            )
        elif pattern == "multi_corridor":
            hints.append(
                {
                    "type": "area_coordination",
                    "problem_turn": f"{t.get('entry')}{t.get('turn')}",
                    "sources": t.get("sources"),
                }
            )
    return hints


def select_problem_turns(
    by_turn: list[dict[str, Any]],
    nlu: NluResult | None,
    *,
    trigger_saturation: float,
) -> list[dict[str, Any]]:
    """问题转向 = 饱和度 ≥ trigger 的转向（含 dir8_code/turn_dir_no）。"""
    out: list[dict[str, Any]] = []
    for row in by_turn:
        sat = _as_float(row.get("turn_saturation"))
        if sat is None or sat < trigger_saturation:
            continue
        if row.get("dir8_code") is None or row.get("turn_dir_no") is None:
            continue
        out.append(row)
    return out


class FlowTraceService:
    """Fetch + analyze upstream flow trace for problem turns."""

    def __init__(
        self,
        pool: PostgresPool | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._pool = pool or PostgresPool()
        self._settings = settings or get_settings()

    async def build(
        self,
        inter_id: str,
        nlu: NluResult | None,
        *,
        data_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Build flow_trace contract. 按问题进口道触发，一跳上一路口 + 100 辆模型。"""
        coverage_high = threshold_value("flow_trace", "coverage_high", default=70.0)
        gap_significant = threshold_value("flow_trace", "gap_significant", default=25.0)
        trigger_sat = threshold_value("flow_trace", "trigger_saturation", default=0.90)
        top_sources = int(threshold_value("flow_trace", "top_sources", default=3))

        by_turn = ((data_payload.get("granularity") or {}).get("by_turn")) or []
        problem_entries = select_problem_entries(by_turn, trigger_saturation=trigger_sat)
        problem_turns = select_problem_turns(by_turn, nlu, trigger_saturation=trigger_sat)
        if not problem_entries:
            return {"available": False, "reason": "not_triggered"}

        tp = nlu.time_period if nlu else None
        period_type = period_type_from_label(tp.label if tp else None)
        from intersection_agent.utils.data_window import build_data_window

        day_basis = "工作日"
        day_labels = ["工作日", "周一", "周二", "周三", "周四", "周五"]
        if tp is not None:
            window = build_data_window(tp)
            day_labels = day_labels_for_filter(window.dow_filter)
            day_basis = day_labels[0]

        if self._settings.mock_db:
            rows = self._mock_rows(inter_id, problem_turns)
        else:
            rows = await self._fetch_upstream(inter_id, period_type, day_labels)
        if not rows:
            return {"available": False, "reason": "no_data", "period_type": period_type}

        grouped = lock_one_hop(rows)
        entry_traces = build_entry_traces(grouped, problem_entries, by_turn)
        if not entry_traces:
            return {"available": False, "reason": "no_match", "period_type": period_type}

        turns = build_problem_turn_trace(
            grouped,
            problem_turns,
            coverage_high=coverage_high,
            gap_significant=gap_significant,
            top_sources=top_sources,
        )
        hints = governance_hints_from_entries(entry_traces) or governance_hints_from_trace(turns)
        return {
            "available": True,
            "period_type": period_type,
            "day_basis": day_basis,
            "caveat": "near_month_pattern",
            "vehicles_base": 100,
            "entry_traces": entry_traces,
            "problem_turns": turns,
            "governance_hints": hints,
        }

    async def _fetch_upstream(
        self, inter_id: str, period_type: str, day_labels: list[str]
    ) -> list[dict[str, Any]]:
        await self._pool.connect()
        flow_schema = self._settings.pg_flow_schema
        road_schema = self._settings.pgschema
        version_id = self._settings.pg_version_id
        sql = f"""
            SELECT fc.f_dir8_no, fc.turn_dir_no,
                   fc.cor_inter_id, fc.cor_f_dir8_no, fc.cor_turn_dir_no,
                   fc.flow_share_ratio,
                   cor.inter_name AS cor_inter_name,
                   ST_X(ST_GeomFromText(cor.geom_center)) AS cor_lng,
                   ST_Y(ST_GeomFromText(cor.geom_center)) AS cor_lat
            FROM {flow_schema}.dws_tfc_inter_turn_flow_correlate_m fc
            LEFT JOIN {road_schema}.dim_inter_info cor
              ON cor.inter_id = fc.cor_inter_id AND cor.version_id = $3
            WHERE fc.inter_id = $1 AND fc.trace_type = 'UPSTREAM' AND fc.is_deleted = 0
              AND fc.period_type = $2
              AND fc.day_of_week = ANY($4::text[])
              AND fc.month = (
                  SELECT MAX(m.month) FROM {flow_schema}.dws_tfc_inter_turn_flow_correlate_m m
                  WHERE m.inter_id = $1 AND m.is_deleted = 0
              )
        """
        try:
            records = await self._pool.fetch(
                sql, inter_id, period_type, version_id, day_labels
            )
        except Exception as exc:  # noqa: BLE001 - 溯源失败不应阻断主诊断
            logger.warning("flow_trace fetch failed: %s", exc)
            return []
        return [dict(r) for r in records]

    @staticmethod
    def _mock_rows(inter_id: str, problem_turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """MOCK_DB：为问题转向造一条强主导上游 + 一条弱来源。"""
        rows: list[dict[str, Any]] = []
        for pt in problem_turns:
            d8 = int(pt["dir8_code"])
            tn = int(pt["turn_dir_no"])
            rows.append(
                {
                    "f_dir8_no": d8, "turn_dir_no": tn,
                    "cor_inter_id": f"mock_up_{d8}{tn}", "cor_f_dir8_no": d8,
                    "cor_turn_dir_no": 2, "flow_share_ratio": 88.0,
                    "cor_inter_name": "上游演示路口", "cor_lng": 117.1, "cor_lat": 36.65,
                }
            )
            rows.append(
                {
                    "f_dir8_no": d8, "turn_dir_no": tn,
                    "cor_inter_id": f"mock_up2_{d8}{tn}", "cor_f_dir8_no": d8,
                    "cor_turn_dir_no": 2, "flow_share_ratio": 40.0,
                    "cor_inter_name": "上游演示路口二跳", "cor_lng": 117.2, "cor_lat": 36.66,
                }
            )
        return rows


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
