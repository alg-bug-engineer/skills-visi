"""Expert static diagnosis logic: phase-channel match, lane-flow match, funnel effect.

Implements the simplified methods in
`skillpacks/intersection/common/专家经验调试/路口交通问题诊断方法.md`:
§1 rules A–D, §2 rules A–D, §3 rules A–B.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any, Callable

_SCRIPT_DIR = Path(__file__).resolve().parent
_SCENE_SCRIPTS = _SCRIPT_DIR.parents[1] / "scene-cognition" / "scripts"

DIRECTION_ORDER = {"北": 0, "东北": 1, "东": 2, "东南": 3, "南": 4, "西南": 5, "西": 6, "西北": 7}
OPPOSITE_DIR4 = {"东": "西", "西": "东", "南": "北", "北": "南", "东南": "西北", "西北": "东南", "东北": "西南", "西南": "东北"}

TURN_MOVE_STRAIGHT = frozenset({"11"})
TURN_MOVE_LEFT = frozenset({"12", "21", "22", "32"})
TURN_MOVE_RIGHT = frozenset({"13", "23"})
TURN_MOVE_UTURN = frozenset({"14", "24"})


def _load_traffic_metrics_logic():
    spec = importlib.util.spec_from_file_location("traffic_metrics_logic", _SCENE_SCRIPTS / "traffic_metrics_logic.py")
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_TML = _load_traffic_metrics_logic()


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _compact_dir4(label: Any) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    for suffix in ("进口", "出口"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    for prefix in ("东南", "西南", "东北", "西北", "东", "西", "南", "北"):
        if text.startswith(prefix) or prefix in text[:3]:
            return prefix
    return text


def _normalize_turn_token(turn_move: Any) -> str:
    return str(turn_move or "").strip().upper()


def classify_lane_function(row: dict[str, Any]) -> dict[str, Any]:
    """Classify a channelization lane row into movement capabilities."""
    turn_move = _normalize_turn_token(row.get("turn_move") or row.get("lane_func_code"))
    lane_info = str(row.get("lane_info") or row.get("lane_func") or "").lower()
    text = f"{turn_move} {lane_info}"

    left = straight = right = uturn = False
    if turn_move in TURN_MOVE_STRAIGHT or turn_move == "11":
        straight = True
    elif turn_move in TURN_MOVE_LEFT:
        left = True
        if turn_move in {"21", "22", "32"}:
            straight = turn_move in {"21", "32"}
            right = turn_move == "22"
    elif turn_move in TURN_MOVE_RIGHT:
        right = True
    elif turn_move in TURN_MOVE_UTURN:
        uturn = True

    if any(k in text for k in ("左直", "直左", "混行")):
        left, straight = True, True
    if any(k in text for k in ("直右", "右直")):
        straight, right = True, True
    if any(k in text for k in ("左右", "左+右")):
        left, right = True, True
    if "左转" in text or "left" in text:
        left = True
    if "直行" in text or "straight" in text or re.search(r"\d+\s*直", text):
        straight = True
    if "右转" in text or "right" in text:
        right = True
    if "调头" in text or "掉头" in text or "uturn" in text:
        uturn = True

    dedicated_left = left and not straight and not right
    dedicated_straight = straight and not left and not right
    dedicated_right = right and not left and not straight
    mixed = sum([left, straight, right]) >= 2

    return {
        "left": left,
        "straight": straight,
        "right": right,
        "uturn": uturn,
        "dedicated_left": dedicated_left,
        "dedicated_straight": dedicated_straight,
        "dedicated_right": dedicated_right,
        "mixed_left_straight": left and straight and not right,
        "mixed": mixed,
        "label": turn_move or lane_info or "unknown",
    }


def _group_channelization_by_direction(channelization: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in channelization:
        if not isinstance(row, dict):
            continue
        role = str(row.get("link_role") or "").lower()
        if role and role != "entrance":
            continue
        direction = _compact_dir4(row.get("dir4_label") or row.get("dir8_label") or row.get("direction"))
        if not direction:
            continue
        grouped.setdefault(direction, []).append(row)
    return grouped


def _group_exits_by_direction(channelization: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in channelization:
        if not isinstance(row, dict):
            continue
        role = str(row.get("link_role") or "").lower()
        if role and role != "exit":
            continue
        direction = _compact_dir4(row.get("dir4_label") or row.get("dir8_label") or row.get("direction"))
        if not direction:
            continue
        grouped.setdefault(direction, []).append(row)
    return grouped


def _approach_lane_summary(lanes: list[dict[str, Any]]) -> dict[str, Any]:
    functions = [classify_lane_function(row) for row in lanes]
    lane_count = len(lanes) if lanes else 0
    parts: list[str] = []
    for fn in functions:
        if fn["dedicated_left"]:
            parts.append("左转专用")
        elif fn["mixed_left_straight"]:
            parts.append("左直混行")
        elif fn["dedicated_straight"]:
            parts.append("直行")
        elif fn["dedicated_right"]:
            parts.append("右转")
        elif fn["mixed"]:
            parts.append("混行")
        elif fn["uturn"]:
            parts.append("调头")
    return {
        "lane_count": lane_count,
        "functions": functions,
        "function_string": "+".join(parts) if parts else "",
        "has_dedicated_left": any(f["dedicated_left"] for f in functions),
        "has_dedicated_straight": any(f["dedicated_straight"] or f["mixed_left_straight"] for f in functions),
        "has_dedicated_right": any(f["dedicated_right"] for f in functions),
        "has_mixed_left_straight": any(f["mixed_left_straight"] for f in functions),
        "has_uturn": any(f["uturn"] for f in functions),
        "straight_lane_count": sum(1 for f in functions if f["straight"] and not f["left"] and not f["right"]),
        "effective_straight_count": sum(1 for f in functions if f["straight"]),
    }


def _parse_movement_atom(value: str) -> tuple[str, set[str]] | None:
    if _TML is not None:
        atom = _TML._movement_key_to_atomish(value)
        split = _TML._split_motor_atom(atom)
        if split:
            direction, turns = split
            return direction, set(turns)
    text = str(value or "").strip()
    for suffix in ("进口", "出口"):
        text = text.replace(suffix, "")
    text = text.replace("左转", "左").replace("直行", "直").replace("右转", "右").replace("调头", "掉")
    i = 0
    while i < len(text) and text[i] in "东南西北":
        i += 1
    direction, turn = text[:i], text[i:]
    if direction and turn:
        return direction, set(turn)
    return None


def _stage_release_atoms(stage: dict[str, Any]) -> list[tuple[str, set[str]]]:
    movements: list[str] = []
    if _TML is not None:
        movements = _TML._stage_movements(stage)
    else:
        text = str(stage.get("release_movements") or "").strip()
        if text:
            movements = [t.strip() for t in text.replace(",", "、").split("、") if t.strip()]
    atoms: list[tuple[str, set[str]]] = []
    for movement in movements:
        parsed = _parse_movement_atom(movement)
        if parsed:
            direction, turns = parsed
            if "右" not in turns:
                atoms.append((direction, turns))
    return atoms


def _direction_delta(dir_a: str, dir_b: str) -> int | None:
    idx_a = DIRECTION_ORDER.get(dir_a)
    idx_b = DIRECTION_ORDER.get(dir_b)
    if idx_a is None or idx_b is None:
        return None
    return (idx_b - idx_a) % 8


def _has_left_protection_phase(direction: str, stages: list[dict[str, Any]]) -> bool:
    for stage in stages:
        for dir_name, turns in _stage_release_atoms(stage):
            if dir_name == direction and ("左" in turns or "掉" in turns):
                return True
    return False


def _left_only_with_opposing_straight(direction: str, stages: list[dict[str, Any]]) -> bool:
    opposing = OPPOSITE_DIR4.get(direction)
    if not opposing:
        return False
    for stage in stages:
        atoms = _stage_release_atoms(stage)
        has_left = any(d == direction and ("左" in t or "掉" in t) for d, t in atoms)
        has_opp_straight = any(d == opposing and "直" in t for d, t in atoms)
        if has_left and has_opp_straight and len(atoms) <= 2:
            return True
    return False


def _movement_released_in_plan(direction: str, turn: str, stages: list[dict[str, Any]]) -> bool:
    for stage in stages:
        for dir_name, turns in _stage_release_atoms(stage):
            if dir_name == direction and turn in turns:
                return True
    return False


def analyze_phase_channel_match(profile: dict[str, Any], th: Callable[[str], float]) -> dict[str, Any]:
    supply = profile.get("supply_profile") or {}
    control = profile.get("control_profile") or {}
    channelization = _as_list(supply.get("channelization") or supply.get("lanes"))
    stages = _as_list(control.get("stage_detail"))
    phase_sequence = _as_list(control.get("phase_sequence"))

    hits: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    approach_details: list[dict[str, Any]] = []

    if not channelization:
        return {"matched": None, "hits": hits, "warnings": warnings, "approach_details": approach_details, "data_gaps": ["channelization"]}

    by_dir = _group_channelization_by_direction(channelization)
    if not stages and not phase_sequence:
        warnings.append({"rule": "gate", "message": "无 stage_detail 且无 phase_sequence，跳过阶段/环图精细判定"})
        if not phase_sequence:
            return {"matched": None, "hits": hits, "warnings": warnings, "approach_details": approach_details, "data_gaps": ["stage_detail", "phase_sequence"]}

    small_lane_threshold = int(th("phase_channel.small_intersection_max_lanes"))

    if stages:
        for stage in stages:
            stage_no = stage.get("stage_no") or stage.get("stage_seq_no") or "?"
            atoms = _stage_release_atoms(stage)
            green = _as_float(stage.get("green_sec"))
            if green > 0 and not atoms and str(stage.get("release_movements") or "").strip() == "":
                warnings.append({"rule": "D", "stage": stage_no, "message": "有效绿灯但 release_movements 为空，方案解析不完整"})

            by_dir_turns: dict[str, set[str]] = {}
            for dir_name, turns in atoms:
                by_dir_turns.setdefault(dir_name, set()).update(turns)
            for dir_name, turns in by_dir_turns.items():
                if "直" in turns and ("左" in turns or "掉" in turns):
                    summary = _approach_lane_summary(by_dir.get(dir_name, []))
                    if not summary["has_mixed_left_straight"]:
                        warnings.append(
                            {
                                "rule": "C",
                                "stage": stage_no,
                                "message": f"阶段{stage_no}同进口{dir_name}直左同放，需复核渠化与放行组织",
                            }
                        )

            for idx, (dir_a, turns_a) in enumerate(atoms):
                lane_a = _approach_lane_summary(by_dir.get(dir_a, []))
                for dir_b, turns_b in atoms[idx + 1 :]:
                    lane_b = _approach_lane_summary(by_dir.get(dir_b, []))
                    delta = _direction_delta(dir_a, dir_b)
                    if delta is None:
                        continue
                    if delta == 4:
                        a_straight = "直" in turns_a
                        b_left = "左" in turns_b or "掉" in turns_b
                        b_straight = "直" in turns_b
                        a_left = "左" in turns_a or "掉" in turns_a
                        a_left_b_straight = a_left and b_straight
                        if (a_straight and b_left) or a_left_b_straight:
                            max_lanes = max(lane_a["lane_count"], lane_b["lane_count"])
                            if max_lanes >= small_lane_threshold:
                                hits.append(
                                    {
                                        "rule": "A",
                                        "stage": stage_no,
                                        "message": f"阶段{stage_no}对向直左冲突（{dir_a} vs {dir_b}，进口{max_lanes}车道）",
                                        "release": f"{dir_a}{''.join(sorted(turns_a))}+{dir_b}{''.join(sorted(turns_b))}",
                                    }
                                )
                    if delta in {2, 6} and "直" in turns_a and "直" in turns_b:
                        hits.append(
                            {
                                "rule": "B",
                                "stage": stage_no,
                                "message": f"阶段{stage_no}相交方向直行交叉冲突（{dir_a}直 vs {dir_b}直）",
                            }
                        )

        for direction, lanes in by_dir.items():
            summary = _approach_lane_summary(lanes)
            left_phase = _has_left_protection_phase(direction, stages)
            approach_details.append(
                {
                    "direction": direction,
                    "lane_function": summary["function_string"],
                    "left_protection_phase": "有" if left_phase else "无",
                    "matched": not summary["has_dedicated_left"] or left_phase,
                }
            )
            if summary["has_dedicated_left"] and not left_phase:
                hits.append({"rule": "C", "direction": direction, "message": f"{direction}进口左转专用道无保护相位"})
            elif summary["has_dedicated_left"] and _left_only_with_opposing_straight(direction, stages):
                if summary["lane_count"] >= small_lane_threshold:
                    hits.append(
                        {
                            "rule": "C",
                            "direction": direction,
                            "message": f"{direction}进口左转仅与对向直行同放且车道数≥{small_lane_threshold}，等效无保护",
                        }
                    )

            for stage in stages:
                stage_no = stage.get("stage_no") or stage.get("stage_seq_no")
                for dir_name, turns in _stage_release_atoms(stage):
                    if dir_name != direction:
                        continue
                    if "左" in turns and not (summary["functions"] and any(f["left"] for f in summary["functions"])):
                        warnings.append({"rule": "G", "stage": stage_no, "message": f"阶段{stage_no}放行{direction}左转但渠化未解析到左向车道，需复核数据口径"})
                    if "直" in turns and not any(f["straight"] for f in summary["functions"]):
                        warnings.append({"rule": "G", "stage": stage_no, "message": f"阶段{stage_no}放行{direction}直行但渠化未解析到直向车道，需复核数据口径"})

            if summary["has_dedicated_straight"] and not _movement_released_in_plan(direction, "直", stages):
                hits.append({"rule": "D", "direction": direction, "message": f"{direction}进口有直行车道但全方案无直行放行"})
            if summary["has_dedicated_left"] and not _movement_released_in_plan(direction, "左", stages):
                hits.append({"rule": "D", "direction": direction, "message": f"{direction}进口有左转车道但全方案无左转放行"})

    matched = False if hits else True if channelization else None
    if matched and warnings:
        matched = True
    return {"matched": matched, "hits": hits, "warnings": warnings, "approach_details": approach_details, "data_gaps": []}


def _parse_movement_key(key: str, supply: dict[str, Any] | None = None) -> tuple[str, str] | None:
    text = str(key)
    turn_code = ""
    for turn_label, candidate in (("左转", "left"), ("直行", "straight"), ("右转", "right"), ("左", "left"), ("直", "straight"), ("右", "right")):
        if turn_label in text:
            turn_code = candidate
            break
    link_token = text.split("_", 1)[0]
    if link_token and supply:
        for row in _as_list(supply.get("channelization") or supply.get("lanes")):
            if not isinstance(row, dict):
                continue
            role = str(row.get("link_role") or "").lower()
            if role and role != "entrance":
                continue
            link_id = str(row.get("link_id") or "")
            if link_id and (link_id == link_token or link_id.endswith(link_token)):
                direction = _compact_dir4(row.get("dir4_label") or row.get("dir8_label") or row.get("direction"))
                if direction and turn_code:
                    return direction, turn_code
    for direction in ("东", "南", "西", "北", "东北", "东南", "西北", "西南"):
        if not text.startswith(direction):
            continue
        rest = text[len(direction) :]
        for turn_label, turn_code in (("左转", "left"), ("直行", "straight"), ("右转", "right"), ("左", "left"), ("直", "straight"), ("右", "right")):
            if turn_label in rest:
                return direction, turn_code
    return None


def _movement_volumes_by_direction(
    demand: dict[str, Any],
    state: dict[str, Any],
    supply: dict[str, Any] | None = None,
) -> dict[str, dict[str, float]]:
    volumes: dict[str, dict[str, float]] = {}
    movement_volume = demand.get("movement_volume") or {}
    if isinstance(movement_volume, dict):
        for key, value in movement_volume.items():
            parsed = _parse_movement_key(str(key), supply)
            if not parsed:
                continue
            direction, turn = parsed
            volumes.setdefault(direction, {"left": 0.0, "straight": 0.0, "right": 0.0, "total": 0.0})
            amount = _as_float(value)
            if turn == "left":
                volumes[direction]["left"] += amount
            elif turn == "straight":
                volumes[direction]["straight"] += amount
            elif turn == "right":
                volumes[direction]["right"] += amount
            volumes[direction]["total"] += amount

    movement_sat = state.get("movement_saturation") or demand.get("movement_saturation") or {}
    sat_by_dir: dict[str, dict[str, float]] = {}
    if isinstance(movement_sat, dict):
        for key, value in movement_sat.items():
            parsed = _parse_movement_key(str(key), supply)
            if not parsed:
                continue
            direction, turn = parsed
            sat_by_dir.setdefault(direction, {})[turn] = _as_float(value)

    for direction, data in volumes.items():
        data["saturation"] = sat_by_dir.get(direction, {})
    return volumes


def _lane_config_ratio(summary: dict[str, Any]) -> tuple[float, float, float]:
    left = straight = right = 0.0
    for fn in summary["functions"]:
        if fn["mixed_left_straight"]:
            left += 0.5
            straight += 0.5
        elif fn["dedicated_left"]:
            left += 1.0
        elif fn["dedicated_straight"]:
            straight += 1.0
        elif fn["dedicated_right"]:
            right += 1.0
        elif fn["mixed"]:
            served = sum([fn["left"], fn["straight"], fn["right"]])
            if served:
                if fn["left"]:
                    left += 1.0 / served
                if fn["straight"]:
                    straight += 1.0 / served
                if fn["right"]:
                    right += 1.0 / served
    total = left + straight + right
    if total <= 0:
        return 0.0, 0.0, 0.0
    return left / total, straight / total, right / total


def _has_valid_lane_config(summary: dict[str, Any], config_counts: tuple[float, float, float]) -> bool:
    """Lane rows exist but all L/S/R counts are zero => unparseable/missing lane function data."""
    if summary.get("lane_count", 0) <= 0:
        return False
    return sum(config_counts) > 0


def _lane_config_counts(summary: dict[str, Any]) -> tuple[float, float, float]:
    left = straight = right = 0.0
    for fn in summary["functions"]:
        if fn["mixed_left_straight"]:
            left += 0.5
            straight += 0.5
        elif fn["dedicated_left"]:
            left += 1.0
        elif fn["dedicated_straight"]:
            straight += 1.0
        elif fn["dedicated_right"]:
            right += 1.0
        elif fn["mixed"]:
            served = sum([fn["left"], fn["straight"], fn["right"]])
            if served:
                if fn["left"]:
                    left += 1.0 / served
                if fn["straight"]:
                    straight += 1.0 / served
                if fn["right"]:
                    right += 1.0 / served
    return left, straight, right


def _flow_share_ratio(volumes: dict[str, float]) -> tuple[float, float, float]:
    total = volumes.get("total") or sum(volumes.get(k, 0.0) for k in ("left", "straight", "right"))
    if total <= 0:
        return 0.0, 0.0, 0.0
    return volumes.get("left", 0.0) / total, volumes.get("straight", 0.0) / total, volumes.get("right", 0.0) / total


def _fmt_count(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


def _fmt_volume(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


def _fmt_ratio(value: float) -> str:
    return f"{value:.0%}"


def _format_structure_deviation_message(
    direction: str,
    config_counts: tuple[float, float, float],
    config_ratio: tuple[float, float, float],
    flow_volumes: dict[str, float],
    flow_ratio: tuple[float, float, float],
    deviation: float,
    threshold: float,
) -> str:
    config_text = (
        f"左转{_fmt_count(config_counts[0])}、直行{_fmt_count(config_counts[1])}、右转{_fmt_count(config_counts[2])}个车道当量"
        f"（占比{_fmt_ratio(config_ratio[0])}/{_fmt_ratio(config_ratio[1])}/{_fmt_ratio(config_ratio[2])}）"
    )
    flow_text = (
        f"左转{_fmt_volume(flow_volumes.get('left', 0.0))}、直行{_fmt_volume(flow_volumes.get('straight', 0.0))}、"
        f"右转{_fmt_volume(flow_volumes.get('right', 0.0))}pcu/h"
        f"（占比{_fmt_ratio(flow_ratio[0])}/{_fmt_ratio(flow_ratio[1])}/{_fmt_ratio(flow_ratio[2])}）"
    )
    formula = (
        f"|{_fmt_ratio(config_ratio[0])}-{_fmt_ratio(flow_ratio[0])}|"
        f"+|{_fmt_ratio(config_ratio[1])}-{_fmt_ratio(flow_ratio[1])}|"
        f"+|{_fmt_ratio(config_ratio[2])}-{_fmt_ratio(flow_ratio[2])}|"
        f"={deviation:.2f}"
    )
    return (
        f"{direction}进口车道配置为{config_text}，实际流量为{flow_text}；"
        f"车道-流量偏差按左/直/右三类占比差值相加：{formula}，超过阈值{threshold:.2f}，说明车道功能和实际车流方向明显错位"
    )


def _optional_number(*values: Any) -> float | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def analyze_lane_flow_match(profile: dict[str, Any], th: Callable[[str], float]) -> dict[str, Any]:
    supply = profile.get("supply_profile") or {}
    demand = profile.get("demand_profile") or {}
    state = profile.get("traffic_state") or {}
    metrics = profile.get("metrics_summary") or profile.get("metrics") or {}

    channelization = _as_list(supply.get("channelization") or supply.get("lanes"))
    by_dir = _group_channelization_by_direction(channelization)
    volumes_by_dir = _movement_volumes_by_direction(demand, state, supply)

    hits: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    approach_details: list[dict[str, Any]] = []
    has_valid_lane_config = False

    for direction, lanes in by_dir.items():
        summary = _approach_lane_summary(lanes)
        vol = volumes_by_dir.get(direction, {})
        if not vol.get("total"):
            approach_details.append({"direction": direction, "matched": None, "reason": "缺少转向流量"})
            continue

        config = _lane_config_ratio(summary)
        config_counts = _lane_config_counts(summary)
        if not _has_valid_lane_config(summary, config_counts):
            approach_details.append(
                {
                    "direction": direction,
                    "lane_count": summary["lane_count"],
                    "matched": None,
                    "reason": "缺少车道功能配置",
                    "movement_volume": {
                        "left": round(vol.get("left", 0.0), 2),
                        "straight": round(vol.get("straight", 0.0), 2),
                        "right": round(vol.get("right", 0.0), 2),
                        "total": round(vol.get("total", 0.0), 2),
                    },
                }
            )
            continue

        has_valid_lane_config = True
        flow = _flow_share_ratio(vol)
        deviation = sum(abs(c - f) for c, f in zip(config, flow))
        sat = vol.get("saturation") or {}

        left_share, straight_share, right_share = flow
        left_sat = _as_float(sat.get("left"))
        straight_sat = _as_float(sat.get("straight"))

        detail = {
            "direction": direction,
            "lane_count": summary["lane_count"],
            "lane_config": {
                "left": round(config_counts[0], 2),
                "straight": round(config_counts[1], 2),
                "right": round(config_counts[2], 2),
            },
            "movement_volume": {
                "left": round(vol.get("left", 0.0), 2),
                "straight": round(vol.get("straight", 0.0), 2),
                "right": round(vol.get("right", 0.0), 2),
                "total": round(vol.get("total", 0.0), 2),
            },
            "config_ratio": f"{config[0]:.0%}:{config[1]:.0%}:{config[2]:.0%}",
            "flow_ratio": f"{left_share:.0%}:{straight_share:.0%}:{right_share:.0%}",
            "structure_deviation": round(deviation, 2),
            "structure_deviation_formula": (
                f"|{config[0]:.2f}-{left_share:.2f}|+|{config[1]:.2f}-{straight_share:.2f}|+|{config[2]:.2f}-{right_share:.2f}|"
            ),
            "matched": True,
        }

        if left_share >= th("channelization.left_turn_share_high") and not summary["has_dedicated_left"]:
            hits.append({"rule": "A", "direction": direction, "message": "左转需求高但缺左转专用道（含仅混行）"})
            detail["matched"] = False
        elif summary["has_dedicated_left"] and left_share < th("channelization.left_turn_share_low") and left_sat < th("saturation.high") * 0.625:
            warnings.append({"rule": "A", "direction": direction, "message": "左转专用道可能过剩"})

        straight_lanes = summary["effective_straight_count"]
        if (
            straight_share >= th("channelization.straight_share_high")
            and straight_lanes <= 1
            and straight_sat >= th("saturation.high") + 0.05
        ):
            hits.append({"rule": "B", "direction": direction, "message": "直行车流占比较高，但直行可用车道偏少，且直行已接近饱和"})
            detail["matched"] = False

        if deviation >= th("channelization.structure_deviation_index"):
            hits.append(
                {
                    "rule": "C",
                    "direction": direction,
                    "message": _format_structure_deviation_message(
                        direction,
                        config_counts,
                        config,
                        vol,
                        flow,
                        deviation,
                        th("channelization.structure_deviation_index"),
                    ),
                    "lane_config": detail["lane_config"],
                    "movement_volume": detail["movement_volume"],
                    "config_ratio": detail["config_ratio"],
                    "flow_ratio": detail["flow_ratio"],
                    "structure_deviation": detail["structure_deviation"],
                    "structure_deviation_formula": detail["structure_deviation_formula"],
                    "threshold": th("channelization.structure_deviation_index"),
                }
            )
            detail["matched"] = False

        sats = [v for v in sat.values() if v > 0]
        if len(sats) >= 2:
            high = max(sats)
            low = min(sats)
            if high >= th("channelization.saturation_imbalance_high") and low <= th("channelization.saturation_imbalance_low"):
                hits.append({"rule": "D", "direction": direction, "message": "同一进口内不同转向忙闲差异明显：有的方向接近饱和，有的方向利用不足"})
                detail["matched"] = False

        approach_details.append(detail)

    cv = _optional_number(state.get("lane_utilization_cv"), demand.get("lane_utilization_cv"), metrics.get("lane_utilization_cv"))
    mismatch = _optional_number(state.get("lane_mismatch_index"), demand.get("lane_mismatch_index"), metrics.get("lane_mismatch_index"))
    derived_mismatch = max(
        (
            _as_float(detail.get("structure_deviation"))
            for detail in approach_details
            if detail.get("structure_deviation") is not None and detail.get("matched") is not None
        ),
        default=0.0,
    )
    mismatch_for_rule = mismatch if mismatch is not None else (derived_mismatch if has_valid_lane_config else None)

    matched = False if hits else True if approach_details else None
    data_gaps = []
    if cv is None:
        data_gaps.append("lane_utilization_cv")
    if not volumes_by_dir:
        data_gaps.append("movement_volume_by_direction")
    if volumes_by_dir and not has_valid_lane_config:
        data_gaps.append("lane_function_by_direction")
    if volumes_by_dir and not by_dir:
        data_gaps.append("channelization")
    return {
        "matched": matched,
        "hits": hits,
        "warnings": warnings,
        "approach_details": approach_details,
        "lane_utilization_cv": cv,
        "lane_mismatch_index": mismatch_for_rule if (has_valid_lane_config and approach_details) or mismatch is not None else None,
        "data_gaps": data_gaps,
    }


def _is_straight_lane(turn_move: Any) -> bool:
    token = _normalize_turn_token(turn_move)
    if token in TURN_MOVE_STRAIGHT:
        return True
    text = token.lower()
    if any(code in text for code in TURN_MOVE_LEFT | TURN_MOVE_RIGHT):
        return False
    return any(k in text for k in ("直行", "直", "straight", "through"))


def _straight_lane_count_for_direction(lanes: list[dict[str, Any]]) -> int:
    count = 0
    for row in lanes:
        fn = classify_lane_function(row)
        if fn["straight"] and not fn["left"] and not fn["right"]:
            count += 1
    if count:
        return count
    return sum(1 for row in lanes if _is_straight_lane(row.get("turn_move")))


def _total_lanes_for_direction(lanes: list[dict[str, Any]]) -> int:
    if not lanes:
        return 0
    total = sum(int(_as_float(row.get("lane_num"), 1)) for row in lanes)
    return total or len(lanes)


def analyze_funnel_effect(profile: dict[str, Any], th: Callable[[str], float] | None = None) -> dict[str, Any]:
    supply = profile.get("supply_profile") or {}
    channelization = _as_list(supply.get("channelization") or supply.get("lanes"))
    static_flags = {str(item) for item in _as_list(supply.get("static_flags"))}

    hits: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    pair_details: list[dict[str, Any]] = []

    entrances = _group_channelization_by_direction(channelization)
    exits = _group_exits_by_direction(channelization)

    if not entrances and not static_flags:
        return {"matched": None, "hits": hits, "warnings": warnings, "pair_details": pair_details, "data_gaps": ["channelization"]}

    for ent_dir, ent_lanes in entrances.items():
        straight_count = _straight_lane_count_for_direction(ent_lanes)
        if straight_count <= 0:
            continue
        opposite = OPPOSITE_DIR4.get(ent_dir)
        exit_lanes = exits.get(opposite or "", [])
        exit_count = _total_lanes_for_direction(exit_lanes)
        same_exit_count = _total_lanes_for_direction(exits.get(ent_dir, []))
        detail = {
            "direction": ent_dir,
            "straight_lanes": straight_count,
            "opposite_exit_lanes": exit_count,
            "same_exit_lanes": same_exit_count,
            "matched": True,
        }
        if not exit_lanes:
            warnings.append({"rule": "A", "direction": ent_dir, "message": f"{ent_dir}对向无出口 link，无法比对"})
        elif straight_count > exit_count:
            hits.append(
                {
                    "rule": "A",
                    "direction": ent_dir,
                    "message": f"{ent_dir}直行{straight_count}车道→{opposite}出口{exit_count}车道，对向直行漏斗",
                }
            )
            detail["matched"] = False
        pair_details.append(detail)

    if len(entrances) > len(exits) and exits:
        hits.append({"rule": "B", "message": "进口方向数多于出口方向数，出口承接偏紧"})

    matched = False if hits else True if pair_details or entrances else None
    data_gaps: list[str] = []
    if not channelization and not static_flags:
        data_gaps.append("channelization")
    return {"matched": matched, "hits": hits, "warnings": warnings, "pair_details": pair_details, "data_gaps": data_gaps}
