"""Reusable traffic metric logic for intersection scene cognition.

The formulas in this module are adapted from signal_optimization_engine's
preprocessing/index_cal and preprocessing/timing pure functions.  Keep this
file dependency-free so skillpack scripts can run without DB-specific ETL code.
"""

from __future__ import annotations

import statistics
from typing import Any

MAIN_TURN_STRAIGHT = 2
MAIN_TURN_LEFT = 1
MAIN_DIRECTION_FLOW_RATIO = 1.5
MIN_RED_SEC = 20
VEHICLE_HEADWAY_M = 6.5
DEFAULT_SATURATION_FLOW_VPH = 1400.0
START_LOSS_SEC = 2.0

DIRECTION_ORDER = {"北": 0, "东北": 1, "东": 2, "东南": 3, "南": 4, "西南": 5, "西": 6, "西北": 7}
TURN_DIR_LABELS = {1: "左转", 2: "直行", 3: "右转"}
_MOTOR_TURNS = frozenset("直左右掉")


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_saturation(volume: float, capacity: float) -> float:
    return round(volume / capacity, 4) if capacity else 0.0


def saturation_flow_from_headway(headway_s: float, default: float = DEFAULT_SATURATION_FLOW_VPH) -> float:
    headway = to_float(headway_s)
    return round(3600.0 / headway, 2) if headway > 0 else default


def lane_capacity_from_signal(
    saturation_flow_vph: float,
    green_sec: float,
    cycle_sec: float,
    *,
    start_loss_sec: float = START_LOSS_SEC,
) -> float | None:
    cycle = to_float(cycle_sec)
    if cycle <= 0:
        return None
    effective_green = max(to_float(green_sec) - start_loss_sec, 0.0)
    return round(to_float(saturation_flow_vph, DEFAULT_SATURATION_FLOW_VPH) * effective_green / cycle, 4)


def compute_green_utilization(
    turn_saturation: float,
    min_green_time: float,
    green_time_plan: float,
) -> float | None:
    plan_green = to_float(green_time_plan)
    if plan_green <= 0:
        return None
    timing_utilization = (to_float(min_green_time) - START_LOSS_SEC) / plan_green
    return round(max(to_float(turn_saturation), timing_utilization), 4)


def level_of_service(saturation_max: float) -> str:
    saturation = to_float(saturation_max)
    if saturation <= 0.60:
        return "A"
    if saturation <= 0.70:
        return "B"
    if saturation <= 0.80:
        return "C"
    if saturation <= 0.90:
        return "D"
    if saturation <= 1.00:
        return "E"
    return "F"


def unbalance_index(values: list[float]) -> float:
    cleaned = [to_float(value) for value in values if value is not None]
    if len(cleaned) <= 1:
        return 0.0
    return round(statistics.stdev(cleaned), 4)


def aggregate_inter_evaluation(
    turn_saturation_values: list[float],
    green_utilization_values: list[float] | None = None,
) -> dict[str, Any]:
    saturations = [to_float(value) for value in turn_saturation_values if value is not None]
    if not saturations:
        return {}
    saturation_max = round(max(saturations), 4)
    return {
        "saturation_max": saturation_max,
        "saturation_avg": round(sum(saturations) / len(saturations), 4),
        "unbalance_index": unbalance_index(green_utilization_values or []),
        "level_of_service": level_of_service(saturation_max),
        "turn_count": len(saturations),
    }


def select_main_turn_dirs(straight_flow: float, left_flow: float) -> list[int]:
    straight = max(to_float(straight_flow), 0.0)
    left = max(to_float(left_flow), 0.0)
    if straight > left * MAIN_DIRECTION_FLOW_RATIO:
        return [MAIN_TURN_STRAIGHT]
    if left > straight * MAIN_DIRECTION_FLOW_RATIO:
        return [MAIN_TURN_LEFT]
    return [MAIN_TURN_LEFT, MAIN_TURN_STRAIGHT]


def calc_travel_time_sec(link_length_m: float, avg_speed_kmh: float) -> float | None:
    length = to_float(link_length_m)
    speed = to_float(avg_speed_kmh)
    if length <= 0 or speed <= 0:
        return None
    return length / (speed / 3.6)


def calc_stop_times(stop_time_sec: float, avg_red_sec: float) -> float | None:
    delay = to_float(stop_time_sec)
    red = to_float(avg_red_sec)
    if delay < 0 or red <= 0:
        return None
    return delay / red


def calc_queue_len_est_m(
    stop_times: float,
    avg_lane_flow: float,
    link_length_m: float,
    *,
    headway_m: float = VEHICLE_HEADWAY_M,
) -> float | None:
    stops = to_float(stop_times)
    flow = to_float(avg_lane_flow)
    length = to_float(link_length_m)
    if stops < 0 or flow < 0 or length <= 0:
        return None
    return min(stops * flow * headway_m, length)


def should_skip_timing(avg_red_sec: float | None, has_timing: bool) -> bool:
    return (not has_timing) or avg_red_sec is None or avg_red_sec < MIN_RED_SEC


def effective_green_by_movement(stages: list[dict[str, Any]]) -> dict[str, float]:
    greens: dict[str, float] = {}
    for stage in stages:
        green = to_float((stage.get("currentTiming") or {}).get("greenSec") or stage.get("green_sec"))
        for movement in _stage_movements(stage):
            greens[movement] = greens.get(movement, 0.0) + green
    return greens


def flow_green_check(items: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = [
        (
            str(item.get("movementKey") or item.get("movement") or ""),
            to_float(item.get("flowVph") or item.get("turnFlowTotal")),
            to_float(item.get("effectiveGreenS")),
        )
        for item in items
    ]
    pairs = [(key, flow, green) for key, flow, green in pairs if key and flow > 0 and green > 0]
    if len(pairs) < 2:
        return {"spearmanTau": None, "flowShares": [], "greenShares": [], "verdict": "insufficient"}
    flows = [flow for _, flow, _ in pairs]
    greens = [green for _, _, green in pairs]
    tau = _spearman(flows, greens)
    flow_total = sum(flows)
    green_total = sum(greens)
    verdict = "strong" if tau is not None and tau >= 0.8 else "weak" if tau is not None and tau >= 0 else "mismatch"
    return {
        "spearmanTau": tau,
        "flowShares": [round(value / flow_total, 4) for value in flows] if flow_total else [],
        "greenShares": [round(value / green_total, 4) for value in greens] if green_total else [],
        "verdict": verdict,
    }


def build_flow_green_items(
    movement_volume: dict[str, Any],
    stages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    effective_greens = effective_green_by_movement(stages)
    items: list[dict[str, Any]] = []
    for movement, flow in movement_volume.items():
        key = str(movement)
        green = effective_greens.get(key) or effective_greens.get(_movement_key_to_atomish(key)) or 0.0
        if green <= 0:
            continue
        items.append({"movementKey": key, "flowVph": to_float(flow), "effectiveGreenS": green})
    return items


def detect_stage_conflicts(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for stage in stages:
        atoms = [_movement_key_to_atomish(item) for item in _stage_movements(stage)]
        atoms = [atom for atom in dict.fromkeys(atoms) if _split_motor_atom(atom)]
        for idx, atom_a in enumerate(atoms):
            for atom_b in atoms[idx + 1 :]:
                if motor_atoms_direct_conflict(atom_a, atom_b):
                    conflicts.append(
                        {
                            "阶段": stage.get("stage_no") or stage.get("stageKey") or stage.get("stage_seq_no"),
                            "冲突流向": f"{atom_a} vs {atom_b}",
                            "类型": "机动车直接冲突",
                        }
                    )
    return conflicts


def detect_overflows(
    queue_rows: list[dict[str, Any]],
    adjacent_relations: list[dict[str, Any]],
    *,
    queue_ratio_high: float = 0.8,
) -> list[dict[str, Any]]:
    spacing_by_dir = {
        str(row.get("方向") or ""): to_float(row.get("间距"))
        for row in adjacent_relations
        if to_float(row.get("间距")) > 0
    }
    overflows: list[dict[str, Any]] = []
    for row in queue_rows:
        direction = str(row.get("进口道") or row.get("进口方向") or "")
        turn = str(row.get("转向") or "")
        queue_values = row.get("最大排队长度") if isinstance(row.get("最大排队长度"), dict) else row
        storage_values = row.get("排队存储比") if isinstance(row.get("排队存储比"), dict) else {}
        for period, queue in (queue_values or {}).items():
            queue_m = to_float(queue)
            storage_ratio = to_float((storage_values or {}).get(period))
            spacing = spacing_by_dir.get(direction)
            if queue_m <= 0:
                continue
            if storage_ratio >= queue_ratio_high or (spacing and queue_m >= spacing * queue_ratio_high):
                overflows.append(
                    {
                        "时段": period,
                        "进口方向": direction,
                        "转向": turn,
                        "最大排队": round(queue_m, 2),
                        "存储比": round(storage_ratio, 4) if storage_ratio else None,
                        "风险": "排队接近存储空间" if storage_ratio else "排队接近相邻路口间距",
                    }
                )
    return overflows


def motor_atoms_direct_conflict(atom_a: str, atom_b: str) -> bool:
    sp_a = _split_motor_atom(atom_a)
    sp_b = _split_motor_atom(atom_b)
    if not sp_a or not sp_b:
        return False
    dir_a, turns_a = sp_a
    dir_b, turns_b = sp_b
    idx_a = DIRECTION_ORDER.get(dir_a)
    idx_b = DIRECTION_ORDER.get(dir_b)
    if idx_a is None or idx_b is None:
        return False
    delta = (idx_b - idx_a) % 8
    return any(_motor_turns_conflict(ta, tb, delta) for ta in turns_a for tb in turns_b)


def _stage_movements(stage: dict[str, Any]) -> list[str]:
    movements: list[str] = []
    for item in stage.get("phaseDirInfoDTOList") or stage.get("phase_dir_info_list") or []:
        key = str(item.get("movementKey") or item.get("movement") or "").strip()
        if key:
            movements.append(key)
    text = str(stage.get("release_movements") or "").strip()
    if text:
        for token in text.replace(",", "、").replace("|", "、").split("、"):
            token = token.strip()
            if token:
                movements.append(token)
    return list(dict.fromkeys(movements))


def _movement_key_to_atomish(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for suffix in ("进口", "出口"):
        text = text.replace(suffix, "")
    text = text.replace("_左转", "左").replace("_直行", "直").replace("_右转", "右")
    text = text.replace("左转", "左").replace("直行", "直").replace("右转", "右").replace("调头", "掉")
    if "_" in text:
        text = text.split("_", 1)[-1] if not any(direction in text for direction in DIRECTION_ORDER) else text.replace("_", "")
    return text


def _split_motor_atom(atom: str) -> tuple[str, frozenset[str]] | None:
    i = 0
    while i < len(atom) and atom[i] in "东南西北":
        i += 1
    direction, turn = atom[:i], atom[i:]
    if not direction or not turn:
        return None
    if any(ch not in _MOTOR_TURNS for ch in turn):
        return None
    return direction, frozenset(turn)


def _motor_turns_conflict(turn_a: str, turn_b: str, dir_delta: int) -> bool:
    if dir_delta == 0:
        return False
    if dir_delta == 4:
        left_like = {"左", "掉"}
        opposing = {"直", "右"}
        return (turn_a in left_like and turn_b in opposing) or (
            turn_b in left_like and turn_a in opposing
        )
    if dir_delta in {2, 6}:
        return turn_a != "右" or turn_b != "右"
    return turn_a != "右" or turn_b != "右"


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    rx = _ranks(xs)
    ry = _ranks(ys)
    mean_x = sum(rx) / len(rx)
    mean_y = sum(ry) / len(ry)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(rx, ry))
    den_x = sum((x - mean_x) ** 2 for x in rx) ** 0.5
    den_y = sum((y - mean_y) ** 2 for y in ry) ** 0.5
    if den_x == 0 or den_y == 0:
        return None
    return round(numerator / (den_x * den_y), 4)


def _ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    idx = 0
    while idx < len(indexed):
        end = idx + 1
        while end < len(indexed) and indexed[end][1] == indexed[idx][1]:
            end += 1
        rank = (idx + end + 1) / 2.0
        for original_idx, _ in indexed[idx:end]:
            ranks[original_idx] = rank
        idx = end
    return ranks
