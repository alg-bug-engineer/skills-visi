"""相位阶段与交通流最小绿计算.

规则（与业务约定一致）：
    1. 机动车车流（不考虑行人跟随放行）最小绿默认 14 秒。
    2. 阶段最小绿由该阶段放行的交通流（机动车流 + 行人过街流）推导：
       - 仅在本阶段放行的交通流：阶段最小绿 ≥ 这些交通流最小绿的最大值；
       - 跨多个阶段放行的交通流：其覆盖各阶段的最小绿加和 ≥ 该交通流最小绿，
         不足部分按各阶段历史绿灯时长加权分摊。
    3. 行人过街流最小绿 = 安全过街时间 = 跨越车道数 × 3.25m ÷ 1.2m/s，
       跨越车道数 = 该方位进口车道数 + 出口车道数（如北行人 = 北进口 + 北出口）。
    4. 若历史方案中某阶段实际放行（绿灯）时间比计算值更短，则取实际更小值；
       现状绿灯为 0 的搭接切片阶段最小绿取 0。
    5. 无对应交通流的阶段：最小绿与最大绿直接沿用历史方案数值（钉死为历史绿灯时长）；
       现状绿灯为 0 时取 0，不回退到库内最小绿兜底值。
    6. 分时段：调用方按时段传入各阶段实际绿灯（actual_green_overrides），
       即可得到各时段独立的最小绿/最大绿。
    7. 稳定性下限（优化器/库内写回时叠加）：原方案绿灯 > 30s 的阶段，
       有效最小绿 ≥ 原方案绿灯 × 60%（向上取整）。

输入输出均为纯数据结构，不依赖数据库，便于单测与多数据源复用。
"""

from __future__ import annotations

from math import ceil
from typing import Any

DEFAULT_MOTOR_MIN_GREEN_S = 14
DEFAULT_LANE_WIDTH_M = 3.25
DEFAULT_PED_WALK_SPEED_MPS = 1.2
HISTORY_GREEN_STABILITY_FLOOR_THRESHOLD_S = 30
HISTORY_GREEN_STABILITY_FLOOR_RATIO = 0.6

_FLOW_TYPE_MOTOR = "motor"
_FLOW_TYPE_PED = "ped"


def pedestrian_min_green_s(
    crossing_lane_count: int,
    *,
    lane_width_m: float = DEFAULT_LANE_WIDTH_M,
    walk_speed_mps: float = DEFAULT_PED_WALK_SPEED_MPS,
) -> int:
    """行人安全过街时间（秒，向上取整）：车道数 × 车道宽 ÷ 步行速度."""
    if crossing_lane_count <= 0:
        return 0
    return ceil(crossing_lane_count * lane_width_m / walk_speed_mps)


def history_green_stability_floor_s(history_green: float | None) -> int | None:
    """原方案绿灯超过阈值时的最小绿稳定性下限（秒，向上取整）."""
    if history_green is None or history_green <= HISTORY_GREEN_STABILITY_FLOOR_THRESHOLD_S:
        return None
    return max(1, int(ceil(history_green * HISTORY_GREEN_STABILITY_FLOOR_RATIO)))


def apply_history_green_stability_floor(min_green: int, history_green: float | None) -> int:
    """叠加规则 7：原方案长阶段（绿灯 > 30s）最小绿不低于原方案绿灯的 60%."""
    floor = history_green_stability_floor_s(history_green)
    if floor is None:
        return min_green
    return max(min_green, floor)


def compute_stage_green_bounds(
    stages: list[dict[str, Any]],
    crossing_lanes_by_dir: dict[int, int] | None = None,
    *,
    motor_min_green_s: int = DEFAULT_MOTOR_MIN_GREEN_S,
    lane_width_m: float = DEFAULT_LANE_WIDTH_M,
    walk_speed_mps: float = DEFAULT_PED_WALK_SPEED_MPS,
    actual_green_overrides: dict[str, float] | None = None,
) -> dict[str, Any]:
    """计算各阶段最小绿/最大绿.

    参数
    ----
    stages: 每个阶段一个 dict：
        - stageKey: 阶段标识（如 "S1"）
        - motorFlows: [(dir8No, turnDirNo), ...] 机动车流（0 基 8 方向编码）
        - pedDirs: [dir8No, ...] 行人过街流方位（0 基）
        - historyGreenS / historyMinGreenS / historyMaxGreenS: 历史方案数值（可缺省）
    crossing_lanes_by_dir: {dir8No: 该方位进口+出口车道数}，用于行人最小绿。
    actual_green_overrides: {stageKey: 实际绿灯秒}，分时段计算时传入该时段
        实际放行时间，参与规则 4 的"取更小值"；缺省用 historyGreenS。

    返回
    ----
    {
        "stages": {stageKey: {"minGreenS", "maxGreenS", "pinnedToHistory", "notes"}},
        "flows": {flowKey: {"flowType", "label", "minGreenS", "stageKeys"}},
    }
    """
    crossing_lanes_by_dir = crossing_lanes_by_dir or {}
    actual_green_overrides = actual_green_overrides or {}

    stage_keys: list[str] = []
    history_green: dict[str, float | None] = {}
    for idx, stage in enumerate(stages):
        key = str(stage.get("stageKey") or f"S{idx + 1}")
        stage_keys.append(key)
        history_green[key] = _to_positive_float(stage.get("historyGreenS"))

    # ── 1. 交通流最小绿 ────────────────────────────────────────────
    # flowKey -> {"flowType", "label", "minGreenS", "stageKeys", "notes"}
    flows: dict[str, dict[str, Any]] = {}
    for idx, stage in enumerate(stages):
        key = stage_keys[idx]
        for raw in stage.get("motorFlows") or []:
            dir8_no, turn_dir_no = int(raw[0]), int(raw[1])
            flow_key = f"motor:{dir8_no}-{turn_dir_no}"
            entry = flows.setdefault(
                flow_key,
                {
                    "flowType": _FLOW_TYPE_MOTOR,
                    "label": f"机动车 dir8={dir8_no} turn={turn_dir_no}",
                    "minGreenS": int(motor_min_green_s),
                    "stageKeys": [],
                    "notes": [],
                },
            )
            if key not in entry["stageKeys"]:
                entry["stageKeys"].append(key)
        for raw_dir in stage.get("pedDirs") or []:
            dir8_no = int(raw_dir)
            flow_key = f"ped:{dir8_no}"
            entry = flows.get(flow_key)
            if entry is None:
                lanes = crossing_lanes_by_dir.get(dir8_no)
                notes: list[str] = []
                if lanes and lanes > 0:
                    min_green = pedestrian_min_green_s(
                        lanes,
                        lane_width_m=lane_width_m,
                        walk_speed_mps=walk_speed_mps,
                    )
                else:
                    # 无渠化数据时无法推算过街时间，按机动车最小绿兜底
                    min_green = int(motor_min_green_s)
                    notes.append("无该方位车道数据，行人最小绿按机动车最小绿兜底")
                entry = flows[flow_key] = {
                    "flowType": _FLOW_TYPE_PED,
                    "label": f"行人 dir8={dir8_no}",
                    "minGreenS": min_green,
                    "crossingLaneCount": lanes,
                    "stageKeys": [],
                    "notes": notes,
                }
            if key not in entry["stageKeys"]:
                entry["stageKeys"].append(key)

    # ── 2. 仅单阶段放行的交通流 → 阶段基础最小绿 ─────────────────
    min_green_by_stage: dict[str, float] = {key: 0.0 for key in stage_keys}
    for flow in flows.values():
        if len(flow["stageKeys"]) == 1:
            key = flow["stageKeys"][0]
            min_green_by_stage[key] = max(min_green_by_stage[key], float(flow["minGreenS"]))

    # ── 3. 跨多阶段交通流：加和约束，不足部分按历史绿灯加权分摊 ──
    multi_stage_flows = sorted(
        (flow for flow in flows.values() if len(flow["stageKeys"]) > 1),
        key=lambda flow: -float(flow["minGreenS"]),
    )
    for flow in multi_stage_flows:
        keys = flow["stageKeys"]
        deficit = float(flow["minGreenS"]) - sum(min_green_by_stage[k] for k in keys)
        if deficit <= 0:
            continue
        weights = [history_green.get(k) or 1.0 for k in keys]
        total_weight = sum(weights) or float(len(keys))
        for k, w in zip(keys, weights):
            min_green_by_stage[k] += deficit * w / total_weight

    # ── 4/5. 历史方案修正与无流量阶段处理 ─────────────────────────
    stage_results: dict[str, dict[str, Any]] = {}
    stage_has_flow = {
        key: any(key in flow["stageKeys"] for flow in flows.values())
        for key in stage_keys
    }
    for idx, stage in enumerate(stages):
        key = stage_keys[idx]
        history_min = _to_positive_float(stage.get("historyMinGreenS"))
        history_max = _to_positive_float(stage.get("historyMaxGreenS"))
        history_raw = _to_non_negative_float(stage.get("historyGreenS"))
        history = history_green[key]
        actual = _to_positive_float(actual_green_overrides.get(key))
        notes: list[str] = []

        if not stage_has_flow[key]:
            # 规则 5：无对应交通流，最小绿/最大绿沿用历史方案数值
            if history_raw is not None and history_raw <= 0:
                min_green = 0
                max_green = 0
                notes.append("阶段无对应交通流且现状绿灯为 0，最小绿/最大绿取 0")
            else:
                pinned = history if history is not None else history_min
                min_green = _to_int_or_none(pinned)
                max_green = _to_int_or_none(history if history is not None else history_max)
                notes.append("阶段无对应交通流，最小绿/最大绿沿用历史方案数值")
            stage_results[key] = {
                "minGreenS": min_green,
                "maxGreenS": max_green,
                "pinnedToHistory": True,
                "notes": notes,
            }
            continue

        min_green = ceil(min_green_by_stage[key] - 1e-9)
        # 规则 4：历史实际放行时间更短时取更小值；现状绿灯 0 的搭接切片取 0
        if history_raw is not None and history_raw <= 0 and min_green > 0:
            min_green = 0
            notes.append("现状绿灯为 0（搭接切片），最小绿取 0")
        else:
            for candidate in (actual, history):
                if candidate is not None and candidate < min_green:
                    min_green = int(candidate)
                    notes.append(f"历史实际放行 {candidate:g}s 短于计算最小绿，按实际取值")
                    break

        max_green = _to_int_or_none(history_max)
        if max_green is not None and min_green > max_green:
            min_green = max_green
            notes.append("计算最小绿超过历史最大绿，按最大绿截断")
        stage_results[key] = {
            "minGreenS": max(0, min_green),
            "maxGreenS": max_green,
            "pinnedToHistory": False,
            "notes": notes,
        }

    return {"stages": stage_results, "flows": flows}


def _to_positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _to_non_negative_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _to_int_or_none(value: Any) -> int | None:
    number = _to_positive_float(value)
    return int(round(number)) if number is not None else None
