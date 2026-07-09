"""line 综合评价指标计算逻辑（skillpackages/linevalindex.md）。"""

from __future__ import annotations

import json
from typing import Any

from preprocessing.index_cal.inter_link_status_logic import calc_travel_time_sec

COORD_STOP_TIMES_THRESHOLD = 0.6
TRAVEL_DIR_FORWARD = 1
TRAVEL_DIR_REVERSE = 2
TRAVEL_DIR_LABELS = {TRAVEL_DIR_FORWARD: "正向", TRAVEL_DIR_REVERSE: "反向"}


def link_status_key(*, travel_dir: int, link_row: dict[str, Any]) -> tuple[str, str]:
    """按行驶方向返回 link 状态表 join 键 (inter_id, link_id)。"""
    if travel_dir == TRAVEL_DIR_FORWARD:
        return str(link_row["t_inter_id"]), str(link_row["link_id"])
    return str(link_row["f_inter_id"]), str(link_row["link_id"])


def build_inter_profile(
    *,
    travel_dir: int,
    inter_rows: list[dict[str, Any]],
    link_rows: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """沿行驶顺序返回 (inter_id, entrance_link_id) 列表（不含起点路口）。"""
    if travel_dir == TRAVEL_DIR_FORWARD:
        ordered_inters = sorted(inter_rows, key=lambda r: int(r["seq_no"]))
        ordered_links = sorted(link_rows, key=lambda r: int(r["seq_no"]))
    else:
        ordered_inters = sorted(inter_rows, key=lambda r: int(r["seq_no"]), reverse=True)
        ordered_links = sorted(link_rows, key=lambda r: int(r["seq_no"]), reverse=True)

    profile: list[tuple[str, str]] = []
    for inter in ordered_inters[1:]:
        inter_id = str(inter["inter_id"])
        if travel_dir == TRAVEL_DIR_FORWARD:
            candidates = [lk for lk in ordered_links if str(lk.get("t_inter_id") or "") == inter_id]
            pick_key = "seq_no"
        else:
            candidates = [lk for lk in ordered_links if str(lk.get("f_inter_id") or "") == inter_id]
            pick_key = "seq_no"
        if not candidates:
            continue
        entrance = max(candidates, key=lambda lk: int(lk[pick_key]))
        profile.append((inter_id, str(entrance["link_id"])))
    return profile


def coord_stop_count(raw_stop_times: float | None) -> int:
    """协调口径停车次数：原始 stop_times > 阈值记 1，否则 0。"""
    if raw_stop_times is None:
        return 0
    try:
        value = float(raw_stop_times)
    except (TypeError, ValueError):
        return 0
    return 1 if value > COORD_STOP_TIMES_THRESHOLD else 0


def continuous_stop_sets(
    profile: list[tuple[str, str]],
    stop_times_by_inter: dict[str, float | None],
    *,
    min_len: int = 2,
) -> list[list[str]]:
    """相邻路口均协调口径停车时，合并为连续停车序列。"""
    sets: list[list[str]] = []
    current: list[str] = []
    for inter_id, _ in profile:
        if coord_stop_count(stop_times_by_inter.get(inter_id)) > 0:
            current.append(inter_id)
        else:
            if len(current) >= min_len:
                sets.append(current)
            current = []
    if len(current) >= min_len:
        sets.append(current)
    return sets


def resolve_link_metric(
    link_row: dict[str, Any],
    *,
    travel_dir: int,
    status_lookup: dict[tuple[str, str], dict[str, Any]],
    link_index_lookup: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """优先 inter_link_status；缺失时回退 link_index_5min 估算行程时间。"""
    inter_id, link_id = link_status_key(travel_dir=travel_dir, link_row=link_row)
    length_m = float(link_row.get("length_m") or 0)

    status = status_lookup.get((inter_id, link_id))
    if status and status.get("travel_time_sec") is not None:
        return {
            "travel_time_sec": status.get("travel_time_sec"),
            "stop_time_sec": status.get("stop_time_sec"),
            "delay_index": status.get("delay_index"),
            "stop_times": status.get("stop_times"),
            "link_length_m": float(status.get("link_length_m") or length_m or 0) or None,
            "source": "inter_link_status",
        }

    idx = (link_index_lookup or {}).get(link_id)
    if idx and length_m > 0:
        avg_speed = idx.get("avg_speed_kmh")
        travel_time_sec = (
            calc_travel_time_sec(length_m, float(avg_speed))
            if avg_speed is not None
            else None
        )
        if travel_time_sec is None:
            return None
        return {
            "travel_time_sec": travel_time_sec,
            "stop_time_sec": idx.get("stop_time_sec"),
            "delay_index": idx.get("delay_index"),
            "stop_times": None,
            "link_length_m": length_m,
            "source": "link_index_5min",
        }
    return None


def aggregate_link_metrics(
    link_metrics: list[dict[str, Any]],
    *,
    line_length_m: float,
    total_link_count: int,
) -> dict[str, Any]:
    """汇总 link 级指标为 line 级。"""
    travel_parts = [m["travel_time_sec"] for m in link_metrics if m.get("travel_time_sec") is not None]
    delay_parts = [m["stop_time_sec"] for m in link_metrics if m.get("stop_time_sec") is not None]
    stop_parts = [m["stop_times"] for m in link_metrics if m.get("stop_times") is not None]

    travel_time_sec = sum(travel_parts) if travel_parts else None
    stop_time_sec = sum(delay_parts) if delay_parts else None
    total_stop_times = sum(stop_parts) if stop_parts else None

    weighted_num = 0.0
    weighted_den = 0.0
    for metric in link_metrics:
        delay_index = metric.get("delay_index")
        length_m = metric.get("link_length_m")
        if delay_index is None or length_m is None:
            continue
        try:
            length = float(length_m)
            idx = float(delay_index)
        except (TypeError, ValueError):
            continue
        if length <= 0:
            continue
        weighted_num += idx * length
        weighted_den += length
    delay_index = weighted_num / weighted_den if weighted_den > 0 else None

    valid_count = len(link_metrics)
    covered_length_m = sum(float(m.get("link_length_m") or 0) for m in link_metrics)

    travel_speed_kmh = None
    if travel_time_sec and travel_time_sec > 0:
        # 口径：全长 / 总行程时间；仅当全部 link 均有行程时间时才用 line 全长，避免虚高
        if valid_count == total_link_count and line_length_m > 0:
            travel_speed_kmh = float(line_length_m) / float(travel_time_sec) * 3.6
        elif covered_length_m > 0:
            travel_speed_kmh = covered_length_m / float(travel_time_sec) * 3.6

    return {
        "travel_time_sec": travel_time_sec,
        "stop_time_sec": stop_time_sec,
        "travel_speed_kmh": travel_speed_kmh,
        "delay_index": delay_index,
        "total_stop_times": total_stop_times,
        "valid_link_count": valid_count,
        "covered_length_m": covered_length_m,
    }


def format_continuous_stop_sets_json(
    sets: list[list[str]],
    inter_names: dict[str, str],
) -> str:
    payload = [
        {
            "interIds": ids,
            "interNames": [inter_names.get(i, i) for i in ids],
            "count": len(ids),
        }
        for ids in sets
    ]
    return json.dumps(payload, ensure_ascii=False)


def compute_line_slice_row(
    *,
    line_row: dict[str, Any],
    link_rows: list[dict[str, Any]],
    inter_rows: list[dict[str, Any]],
    inter_names: dict[str, str],
    status_lookup: dict[tuple[str, str], dict[str, Any]],
    link_index_lookup: dict[str, dict[str, Any]] | None = None,
    travel_dir: int,
    day_of_week: int,
    step_index: int,
    calc_version: str = "line_val_index_v1",
) -> dict[str, Any] | None:
    """计算单条 line 在某一方向+时间片的评价行。"""
    ordered_links = sorted(link_rows, key=lambda r: int(r["seq_no"]))
    if travel_dir == TRAVEL_DIR_REVERSE:
        ordered_links = list(reversed(ordered_links))

    link_metrics: list[dict[str, Any]] = []
    for link in ordered_links:
        metric = resolve_link_metric(
            link,
            travel_dir=travel_dir,
            status_lookup=status_lookup,
            link_index_lookup=link_index_lookup,
        )
        if not metric:
            return None
        link_metrics.append(metric)

    if not link_metrics:
        return None

    line_length_m = float(line_row.get("line_length_m") or 0)
    agg = aggregate_link_metrics(
        link_metrics,
        line_length_m=line_length_m,
        total_link_count=len(link_rows),
    )

    profile = build_inter_profile(
        travel_dir=travel_dir,
        inter_rows=inter_rows,
        link_rows=link_rows,
    )
    stop_by_inter: dict[str, float | None] = {}
    for inter_id, entrance_link_id in profile:
        status = status_lookup.get((inter_id, entrance_link_id))
        stop_by_inter[inter_id] = status.get("stop_times") if status else None
    cont_sets = continuous_stop_sets(profile, stop_by_inter)

    return {
        "line_id": line_row["line_id"],
        "travel_dir": travel_dir,
        "day_of_week": day_of_week,
        "step_index": step_index,
        "line_name": line_row.get("line_name"),
        "road_name": line_row.get("road_name"),
        "travel_dir_label": TRAVEL_DIR_LABELS.get(travel_dir),
        "line_length_m": line_length_m or None,
        "link_count": len(link_rows),
        "inter_count": len(inter_rows),
        "travel_time_sec": agg["travel_time_sec"],
        "stop_time_sec": agg["stop_time_sec"],
        "travel_speed_kmh": agg["travel_speed_kmh"],
        "delay_index": agg["delay_index"],
        "total_stop_times": agg["total_stop_times"],
        "continuous_stop_sets_json": format_continuous_stop_sets_json(cont_sets, inter_names),
        "calc_version": calc_version,
        "is_deleted": 0,
    }
