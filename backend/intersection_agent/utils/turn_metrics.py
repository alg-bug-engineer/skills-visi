"""Turn-level saturation metrics — shared normalization for cognition & map."""

from __future__ import annotations

import re
from typing import Any

from intersection_agent.utils.traffic_labels import DIR8_LABELS, TURN_DIR_LABELS

DIR4_TO_GROUP: dict[str, str] = {
    "东": "东西向",
    "西": "东西向",
    "南": "南北向",
    "北": "南北向",
    "东南": "东南向",
    "西南": "西南向",
    "东北": "东北向",
    "西北": "西北向",
}

GROUP_ORDER = ("东西向", "南北向", "东南向", "西南向", "东北向", "西北向", "其他")


def _dir_from_turn_label(label: str) -> str:
    m = re.match(r"([东南西北]+)", str(label or "").strip())
    return m.group(1) if m else ""


def _turn_char_from_label(label: str, turn_dir_no: int | None) -> str:
    m = re.search(r"(左|直|右|调)", str(label or ""))
    if m:
        return m.group(1)
    return TURN_DIR_LABELS.get(int(turn_dir_no or 2), "直")[:1]


def _saturation_level(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 0.85:
        return "high"
    if value >= 0.65:
        return "medium"
    return "low"


def normalize_turn_metrics(by_turn: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalize granularity.by_turn rows for cognition / map (turn-level saturation)."""
    result: list[dict[str, Any]] = []
    for row in by_turn or []:
        label = str(row.get("label") or "").strip()
        if not label:
            dir8 = int(row.get("dir8_code") or 0)
            turn_no = int(row.get("turn_dir_no") or 2)
            dir_part = DIR8_LABELS.get(dir8, "—")
            turn_part = TURN_DIR_LABELS.get(turn_no, "直行")
            label = f"{dir_part}{turn_part}"
        dir4 = _dir_from_turn_label(label)
        turn_dir_no = row.get("turn_dir_no")
        turn_char = _turn_char_from_label(label, int(turn_dir_no) if turn_dir_no is not None else None)
        sat_raw = row.get("turn_saturation")
        sat = float(sat_raw) if sat_raw is not None else None
        gu_raw = row.get("green_utilization")
        gu = float(gu_raw) if gu_raw is not None else None
        result.append(
            {
                "label": label,
                "dir4_label": dir4,
                "turn": turn_char,
                "dir8_code": row.get("dir8_code"),
                "turn_dir_no": turn_dir_no,
                "turn_saturation": round(sat, 4) if sat is not None else None,
                "green_utilization": round(gu, 4) if gu is not None else None,
                "level": _saturation_level(sat),
            }
        )
    result.sort(
        key=lambda t: (t.get("turn_saturation") is None, -(t.get("turn_saturation") or 0)),
    )
    return result


def build_direction_groups_from_turns(
    arms: list[dict[str, Any]],
    metrics_by_turn: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate turn-level saturation into direction groups (max/avg from turns)."""
    group_sats: dict[str, list[float]] = {}
    for turn in metrics_by_turn:
        sat = turn.get("turn_saturation")
        if sat is None or float(sat) <= 0:
            continue
        dir_key = str(turn.get("dir4_label") or _dir_from_turn_label(str(turn.get("label") or "")))
        group = DIR4_TO_GROUP.get(dir_key, dir_key or "其他")
        group_sats.setdefault(group, []).append(float(sat))

    arm_labels_by_group: dict[str, list[str]] = {}
    for arm in arms:
        key = str(arm.get("dir4_label") or "").replace("进口", "").replace("出口", "").strip()
        if not key:
            continue
        group = DIR4_TO_GROUP.get(key, key)
        arm_labels_by_group.setdefault(group, [])
        if key not in arm_labels_by_group[group]:
            arm_labels_by_group[group].append(key)

    groups: list[dict[str, Any]] = []
    for group_name in GROUP_ORDER:
        sats = group_sats.get(group_name)
        if not sats:
            continue
        max_sat = max(sats)
        avg_sat = sum(sats) / len(sats)
        groups.append(
            {
                "group": group_name,
                "saturation_avg": round(avg_sat, 3),
                "saturation_max": round(max_sat, 3),
                "level": _saturation_level(max_sat),
                "arm_labels": arm_labels_by_group.get(group_name, []),
            }
        )
    return groups


def turns_for_dir(metrics_by_turn: list[dict[str, Any]], dir_key: str) -> list[dict[str, Any]]:
    norm = dir_key.replace("进口", "").strip()
    return [
        t
        for t in metrics_by_turn
        if str(t.get("dir4_label") or _dir_from_turn_label(str(t.get("label") or ""))) == norm
        and t.get("turn_saturation") is not None
    ]


def attach_turn_metrics_to_cognition(
    cognition: dict[str, Any],
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Merge granularity.by_turn into cognition.metrics_by_turn; refresh direction_groups."""
    by_turn = ((data.get("granularity") or {}).get("by_turn")) or []
    metrics_by_turn = normalize_turn_metrics(by_turn)
    cognition["metrics_by_turn"] = metrics_by_turn
    if metrics_by_turn:
        cognition["direction_groups"] = build_direction_groups_from_turns(
            cognition.get("arms") or [],
            metrics_by_turn,
        )
    return metrics_by_turn
