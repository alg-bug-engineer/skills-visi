"""干线协调关系挖掘：配时表 + PG 路网相邻关系。

判定标准（三条件同时满足）：
  1. 日期类型相同（day_of_week）
  2. 周期相同（cycle_len_sec）
  3. 路口相邻（PG dim_link_info）
时段不要求一致；组内时段取成员路口配时时段的并集（最早开始、最晚结束）。
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from data.pg_reader import connect_pg
from preprocessing.index_cal.inter_turn_5min_his_mm import (
    _expanded_weekdays,
    _extract_inter_name_from_plan_name,
    _time_to_seconds,
    _to_int,
)
from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

WEEKDAY_NAMES = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
CALC_VERSION = "corridor_coord_v1"


def format_time(seconds: int) -> str:
    seconds = seconds % 86400
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


@dataclass(frozen=True)
class TimingSlot:
    inter_id: str
    day_of_week: int
    start_sec: int
    end_sec: int
    cycle_len_sec: int
    plan_no: int
    ctrl_mode: str | None
    schedule_no: int
    day_plan_no: int
    period_seq_no: int
    inter_name: str = ""


@dataclass
class CoordinationGroup:
    group_id: str
    corridor_id: str
    day_of_week: int
    start_sec: int
    end_sec: int
    cycle_len_sec: int
    inter_ids: list[str] = field(default_factory=list)
    inter_names: dict[str, str] = field(default_factory=dict)
    plan_by_inter: dict[str, int] = field(default_factory=dict)
    ctrl_mode_by_inter: dict[str, str | None] = field(default_factory=dict)
    adjacency_edges: list[tuple[str, str]] = field(default_factory=list)
    link_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "corridor_id": self.corridor_id,
            "date_type": WEEKDAY_NAMES.get(self.day_of_week, str(self.day_of_week)),
            "day_of_week": self.day_of_week,
            "period": {
                "start_time": format_time(self.start_sec),
                "end_time": format_time(self.end_sec),
                "start_sec": self.start_sec,
                "end_sec": self.end_sec,
            },
            "cycle_len_sec": self.cycle_len_sec,
            "intersection_count": len(self.inter_ids),
            "inter_ids": self.inter_ids,
            "inter_names": self.inter_names,
            "plan_by_inter": self.plan_by_inter,
            "ctrl_mode_by_inter": self.ctrl_mode_by_inter,
            "adjacency_edges": [{"from": a, "to": b} for a, b in self.adjacency_edges],
            "connecting_link_ids": self.link_ids,
        }


def fetch_timing_slots(conn: Any) -> list[TimingSlot]:
    schedule_ident = _quote_identifier("dwd_ctl_inter_schedule_cfg")
    period_ident = _quote_identifier("dwd_ctl_inter_day_plan_period")
    plan_ident = _quote_identifier("dwd_ctl_inter_plan_cfg")
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
SELECT sc.inter_id, sc.week_day_no, sc.schedule_no, sc.day_plan_no,
       pp.period_seq_no, pp.start_time, pp.end_time, pp.plan_no, pp.ctrl_mode,
       pc.cycle_len_sec, pc.plan_name
FROM {schedule_ident} sc
JOIN {period_ident} pp
  ON pp.inter_id = sc.inter_id
 AND pp.day_plan_no = sc.day_plan_no
 AND COALESCE(pp.is_deleted, 0) = 0
JOIN {plan_ident} pc
  ON pc.inter_id = pp.inter_id
 AND pc.plan_no = pp.plan_no
 AND COALESCE(pc.is_deleted, 0) = 0
WHERE COALESCE(sc.is_deleted, 0) = 0
ORDER BY sc.inter_id, sc.week_day_no, sc.schedule_no, pp.period_seq_no
""".strip()
        )
        rows = list(cursor.fetchall())

    explicit_weekdays_by_inter: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        week_day_no = _to_int(row.get("week_day_no"), default=None)
        if week_day_no in {1, 2, 3, 4, 5, 6, 7}:
            explicit_weekdays_by_inter[str(row.get("inter_id") or "")].add(week_day_no)

    slots: list[TimingSlot] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        inter_id = str(row.get("inter_id") or "")
        start_sec = _time_to_seconds(row.get("start_time"))
        end_sec = _time_to_seconds(row.get("end_time"))
        cycle_len_sec = _to_int(row.get("cycle_len_sec"), default=0) or 0
        plan_no = _to_int(row.get("plan_no"), default=0) or 0
        if not inter_id or start_sec is None or end_sec is None or cycle_len_sec <= 0:
            continue
        if end_sec <= start_sec:
            end_sec += 86400
        inter_name = _extract_inter_name_from_plan_name(row.get("plan_name"))
        ctrl_mode = str(row.get("ctrl_mode") or "") or None

        for day_of_week in _expanded_weekdays(row, explicit_weekdays_by_inter):
            key = (
                inter_id,
                day_of_week,
                start_sec,
                end_sec,
                cycle_len_sec,
                plan_no,
                _to_int(row.get("schedule_no"), default=0) or 0,
            )
            if key in seen:
                continue
            seen.add(key)
            slots.append(
                TimingSlot(
                    inter_id=inter_id,
                    day_of_week=day_of_week,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    cycle_len_sec=cycle_len_sec,
                    plan_no=plan_no,
                    ctrl_mode=ctrl_mode,
                    schedule_no=_to_int(row.get("schedule_no"), default=0) or 0,
                    day_plan_no=_to_int(row.get("day_plan_no"), default=0) or 0,
                    period_seq_no=_to_int(row.get("period_seq_no"), default=0) or 0,
                    inter_name=inter_name,
                )
            )
    return slots


def _resolve_link_table(conn: Any, schema: str) -> str:
    preferred = (os.getenv("PG_DIM_LINK_TABLE") or "dim_link_info").strip()
    candidates = [preferred]
    if preferred != "dim_link_info":
        candidates.append("dim_link_info")
    with conn.cursor() as cur:
        for table in candidates:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
                LIMIT 1
                """,
                (schema, table),
            )
            if cur.fetchone():
                return table
    return preferred


def fetch_adjacency() -> tuple[
    dict[tuple[str, str], list[str]],
    dict[tuple[str, str], list[str]],
    dict[str, str],
]:
    schema = os.getenv("PGSCHEMA", "road6")
    inter_table = os.getenv("PG_DIM_INTER_TABLE", "dim_inter_info")

    edge_links: dict[tuple[str, str], list[str]] = defaultdict(list)
    edge_road_names: dict[tuple[str, str], list[str]] = defaultdict(list)
    inter_names: dict[str, str] = {}

    with connect_pg() as conn:
        link_table = _resolve_link_table(conn, schema)
        with conn.cursor() as cur:
            qualified_inter = f'"{schema}"."{inter_table}"'
            cur.execute(
                f"""
                SELECT inter_id::text AS inter_id, inter_name
                FROM {qualified_inter}
                WHERE inter_name IS NOT NULL AND btrim(inter_name) <> ''
                """
            )
            for row in cur.fetchall():
                inter_names[str(row["inter_id"])] = str(row["inter_name"])

            qualified_link = f'"{schema}"."{link_table}"'
            cur.execute(
                f"""
                SELECT link_id::text AS link_id,
                       road_name,
                       f_inter_id::text AS f_inter_id,
                       t_inter_id::text AS t_inter_id
                FROM {qualified_link}
                WHERE f_inter_id IS NOT NULL
                  AND t_inter_id IS NOT NULL
                  AND f_inter_id <> t_inter_id
                """
            )
            for row in cur.fetchall():
                a = str(row["f_inter_id"])
                b = str(row["t_inter_id"])
                link_id = str(row["link_id"])
                road_name = str(row.get("road_name") or "").strip()
                edge_key = (a, b) if a < b else (b, a)
                if link_id not in edge_links[edge_key]:
                    edge_links[edge_key].append(link_id)
                if road_name and road_name not in edge_road_names[edge_key]:
                    edge_road_names[edge_key].append(road_name)
    return edge_links, edge_road_names, inter_names


def _pick_representative_slot(slots: list[TimingSlot]) -> TimingSlot:
    """同一路口同上下文多条时段时，取覆盖时长最长的一条作为代表。"""
    return max(slots, key=lambda s: s.end_sec - s.start_sec)


def _aggregate_period_bounds(slots: list[TimingSlot]) -> tuple[int, int]:
    return min(s.start_sec for s in slots), max(s.end_sec for s in slots)


def _connected_components(nodes: set[str], edges: list[tuple[str, str]]) -> list[set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    visited: set[str] = set()
    components: list[set[str]] = []
    for start in sorted(nodes):
        if start in visited:
            continue
        stack = [start]
        comp: set[str] = set()
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            comp.add(node)
            stack.extend(sorted(adj[node] - visited))
        if comp:
            components.append(comp)
    return components


def mine_coordination_groups(
    slots: list[TimingSlot],
    edge_links: dict[tuple[str, str], list[str]],
    inter_names: dict[str, str],
    *,
    min_size: int = 2,
    require_ctrl_mode: str | None = None,
) -> list[CoordinationGroup]:
    slot_index: dict[tuple[int, int], dict[str, list[TimingSlot]]] = defaultdict(lambda: defaultdict(list))
    for slot in slots:
        if require_ctrl_mode and slot.ctrl_mode != require_ctrl_mode:
            continue
        context_key = (slot.day_of_week, slot.cycle_len_sec)
        slot_index[context_key][slot.inter_id].append(slot)

    groups: list[CoordinationGroup] = []
    group_seq = 0

    for (day_of_week, cycle_len_sec), inter_slots_map in sorted(
        slot_index.items(), key=lambda x: (x[0][0], x[0][1], -len(x[1]))
    ):
        if len(inter_slots_map) < min_size:
            continue

        matching_edges: list[tuple[str, str]] = []
        for (a, b), _link_ids in edge_links.items():
            if a in inter_slots_map and b in inter_slots_map:
                matching_edges.append((a, b))

        if not matching_edges:
            continue

        nodes = set(inter_slots_map)
        for comp in _connected_components(nodes, matching_edges):
            if len(comp) < min_size:
                continue
            group_seq += 1
            comp_edges = [(a, b) for a, b in matching_edges if a in comp and b in comp]
            comp_link_ids: list[str] = []
            for a, b in comp_edges:
                edge_key = (a, b) if a < b else (b, a)
                comp_link_ids.extend(edge_links.get(edge_key, []))

            comp_slots = [slot for iid in comp for slot in inter_slots_map[iid]]
            start_sec, end_sec = _aggregate_period_bounds(comp_slots)
            rep_by_inter = {iid: _pick_representative_slot(inter_slots_map[iid]) for iid in comp}
            name_map = {
                iid: inter_names.get(iid) or rep_by_inter[iid].inter_name or iid
                for iid in sorted(comp)
            }
            groups.append(
                CoordinationGroup(
                    group_id=f"CG-{group_seq:04d}",
                    corridor_id="",
                    day_of_week=day_of_week,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    cycle_len_sec=cycle_len_sec,
                    inter_ids=sorted(comp),
                    inter_names=name_map,
                    plan_by_inter={iid: rep_by_inter[iid].plan_no for iid in sorted(comp)},
                    ctrl_mode_by_inter={iid: rep_by_inter[iid].ctrl_mode for iid in sorted(comp)},
                    adjacency_edges=sorted(comp_edges),
                    link_ids=sorted(set(comp_link_ids)),
                )
            )
    return groups


def _extract_road_label(road_name: str) -> str:
    text = road_name.strip()
    if not text:
        return ""
    if ":" in text:
        return text.split(":", 1)[0].strip()
    if "：" in text:
        return text.split("：", 1)[0].strip()
    return text


def order_corridor_chain(
    inter_ids: list[str],
    edges: list[tuple[str, str]],
) -> list[str]:
    node_set = set(inter_ids)
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        if a in node_set and b in node_set:
            adj[a].add(b)
            adj[b].add(a)

    if not node_set:
        return []
    if len(node_set) == 1:
        return [next(iter(node_set))]

    endpoints = sorted(n for n in node_set if len(adj[n]) <= 1)
    start = endpoints[0] if endpoints else min(node_set)

    ordered: list[str] = []
    visited: set[str] = set()
    cur = start
    prev: str | None = None
    while cur is not None:
        ordered.append(cur)
        visited.add(cur)
        nxt: str | None = None
        for nb in sorted(adj[cur]):
            if nb != prev and nb not in visited:
                nxt = nb
                break
        prev, cur = cur, nxt

    for node in sorted(node_set - visited):
        ordered.append(node)
    return ordered


def infer_corridor_name(
    ordered_inter_ids: list[str],
    inter_names: dict[str, str],
    edge_road_names: dict[tuple[str, str], list[str]],
    group_edges: list[tuple[str, str]],
) -> str:
    road_counter: dict[str, int] = defaultdict(int)
    for a, b in group_edges:
        edge_key = (a, b) if a < b else (b, a)
        for road_name in edge_road_names.get(edge_key, []):
            label = _extract_road_label(road_name)
            if label:
                road_counter[label] += 1

    if road_counter:
        primary_road = max(road_counter.items(), key=lambda x: (x[1], x[0]))[0]
        end_names = [
            inter_names.get(iid, iid) for iid in (ordered_inter_ids[0], ordered_inter_ids[-1])
        ]
        if len(set(end_names)) >= 2:
            return f"{primary_road}（{end_names[0]}—{end_names[-1]}）"
        return primary_road

    if len(ordered_inter_ids) >= 2:
        end_names = [
            inter_names.get(iid, iid) for iid in (ordered_inter_ids[0], ordered_inter_ids[-1])
        ]
        return f"{end_names[0]}—{end_names[-1]}"
    if ordered_inter_ids:
        return inter_names.get(ordered_inter_ids[0], ordered_inter_ids[0])
    return "未命名走廊"


def extract_primary_road_name(corridor_name: str) -> str:
    text = corridor_name.strip()
    if not text:
        return ""
    if "（" in text:
        return text.split("（", 1)[0].strip()
    if "(" in text:
        return text.split("(", 1)[0].strip()
    return text


def aggregate_corridors(
    groups: list[CoordinationGroup],
    edge_road_names: dict[tuple[str, str], list[str]],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], list[CoordinationGroup]] = defaultdict(list)
    for group in groups:
        buckets[tuple(sorted(group.inter_ids))].append(group)

    corridors: list[dict[str, Any]] = []
    corridor_id_by_key: dict[tuple[str, ...], str] = {}

    for seq, (corridor_key, bucket) in enumerate(
        sorted(buckets.items(), key=lambda x: (-len(x[0]), x[0])),
        start=1,
    ):
        corridor_id = f"CR-{seq:04d}"
        corridor_id_by_key[corridor_key] = corridor_id
        bucket.sort(
            key=lambda g: (g.day_of_week, g.start_sec, g.end_sec, g.cycle_len_sec, g.group_id)
        )
        anchor = bucket[0]
        ordered_ids = order_corridor_chain(anchor.inter_ids, anchor.adjacency_edges)
        ordered_names = [anchor.inter_names.get(iid, iid) for iid in ordered_ids]

        weekdays = sorted({g.day_of_week for g in bucket})
        periods = sorted({(g.start_sec, g.end_sec) for g in bucket}, key=lambda x: (x[0], x[1]))
        cycles = sorted({g.cycle_len_sec for g in bucket})

        schedule_variants: list[dict[str, Any]] = []
        variant_map: dict[tuple[int, int, int, int], list[CoordinationGroup]] = defaultdict(list)
        for g in bucket:
            variant_map[(g.day_of_week, g.start_sec, g.end_sec, g.cycle_len_sec)].append(g)
        for (dow, start_sec, end_sec, cycle), variant_groups in sorted(variant_map.items()):
            schedule_variants.append(
                {
                    "date_type": WEEKDAY_NAMES.get(dow, str(dow)),
                    "day_of_week": dow,
                    "period": {
                        "start_time": format_time(start_sec),
                        "end_time": format_time(end_sec),
                        "start_sec": start_sec,
                        "end_sec": end_sec,
                    },
                    "cycle_len_sec": cycle,
                    "group_ids": [g.group_id for g in variant_groups],
                    "group_count": len(variant_groups),
                }
            )

        all_link_ids: set[str] = set()
        for g in bucket:
            all_link_ids.update(g.link_ids)

        corridor_name = infer_corridor_name(
            ordered_ids,
            anchor.inter_names,
            edge_road_names,
            anchor.adjacency_edges,
        )
        corridors.append(
            {
                "corridor_id": corridor_id,
                "corridor_name": corridor_name,
                "primary_road_name": extract_primary_road_name(corridor_name),
                "intersection_count": len(corridor_key),
                "inter_ids": ordered_ids,
                "inter_names_ordered": ordered_names,
                "inter_names": anchor.inter_names,
                "topology_key": list(corridor_key),
                "connecting_link_ids": sorted(all_link_ids),
                "schedule_summary": {
                    "group_count": len(bucket),
                    "weekday_count": len(weekdays),
                    "weekdays": [WEEKDAY_NAMES.get(d, str(d)) for d in weekdays],
                    "day_of_week_list": weekdays,
                    "period_count": len(periods),
                    "periods": [
                        {
                            "start_time": format_time(s),
                            "end_time": format_time(e),
                            "start_sec": s,
                            "end_sec": e,
                        }
                        for s, e in periods
                    ],
                    "cycle_len_sec_list": cycles,
                },
                "schedule_variants": schedule_variants,
                "groups": [g.to_dict() for g in bucket],
            }
        )

    for group in groups:
        group.corridor_id = corridor_id_by_key.get(tuple(sorted(group.inter_ids)), "")
    return corridors


def run_corridor_coord_mine(
    *,
    min_size: int = 2,
    require_ctrl_mode: str | None = None,
) -> tuple[list[TimingSlot], list[CoordinationGroup], list[dict[str, Any]]]:
    conn = _get_mysql_connection()
    try:
        slots = fetch_timing_slots(conn)
    finally:
        conn.close()

    edge_links, edge_road_names, inter_names = fetch_adjacency()
    groups = mine_coordination_groups(
        slots,
        edge_links,
        inter_names,
        min_size=min_size,
        require_ctrl_mode=require_ctrl_mode,
    )
    corridors = aggregate_corridors(groups, edge_road_names)
    return slots, groups, corridors
