"""流量溯源：单进口道选择（与用户 NLU 对齐）。"""

from __future__ import annotations

from typing import Any

from intersection_agent.utils.traffic_labels import DIR8_LABELS

# 方向组 → 默认第一个方位 dir8（东西向→东，南北向→北）
_DIRECTION_GROUP_FIRST: dict[str, int] = {
    "东西向": 2,
    "东西": 2,
    "南北向": 0,
    "南北": 0,
    "东南向": 3,
    "东南": 3,
    "西南向": 5,
    "西南": 5,
    "东北向": 1,
    "东北": 1,
    "西北向": 7,
    "西北": 7,
}

_TURN_HINTS = ("左", "直", "右", "调", "掉头")


def _row_dir8(row: dict[str, Any]) -> int | None:
    d8 = row.get("dir8_code")
    if d8 is not None:
        return int(d8)
    label_text = str(row.get("label") or "")
    for code, name in DIR8_LABELS.items():
        if label_text.startswith(name):
            return code
    return None


def _turn_no_from_token(token: str, dir8: int) -> int | None:
    label = DIR8_LABELS.get(dir8, "")
    if not token.startswith(label):
        return None
    if "左" in token:
        return 1
    if "直" in token:
        return 2
    if "右" in token:
        return 3
    if "调" in token:
        return 4
    return None


def resolve_trace_approach(
    directions: list[str] | None,
    by_turn: list[dict[str, Any]],
    *,
    trigger_saturation: float = 0.90,
) -> tuple[int | None, int | None, str | None]:
    """解析唯一溯源进口 (dir8, turn_no, approach_label)。

    优先级：转向语义 > 方向组首方位 > 具体进口 > 最饱和进口。
    无可用进口或均未过饱和时返回 (None, None, None)。
    """
    available = {d8 for r in by_turn if (d8 := _row_dir8(r)) is not None}
    if not available:
        return None, None, None

    saturated = {
        d8
        for r in by_turn
        if (r.get("turn_saturation") or 0.0) >= trigger_saturation
        and (d8 := _row_dir8(r)) is not None
    }

    # P0: 转向语义（西左转）
    for raw in directions or []:
        token = str(raw).strip()
        if not any(h in token for h in _TURN_HINTS):
            continue
        for code, label in DIR8_LABELS.items():
            if token.startswith(label) and code in available:
                return code, _turn_no_from_token(token, code), f"{label}进口"

    # P1: 方向组 → 第一个方位（须在具体进口前缀匹配之前，避免「南北向」误匹配南进口）
    for raw in directions or []:
        token = str(raw).strip()
        first = _DIRECTION_GROUP_FIRST.get(token)
        if first is not None and first in available:
            return first, None, f"{DIR8_LABELS[first]}进口"

    # P2: 具体进口
    for raw in directions or []:
        token = str(raw).strip()
        if token in _DIRECTION_GROUP_FIRST:
            continue
        for code, label in DIR8_LABELS.items():
            if token.startswith(label) and code in available:
                return code, None, f"{label}进口"

    # P3: 最饱和进口
    if saturated:
        top_row = max(
            (r for r in by_turn if _row_dir8(r) in saturated),
            key=lambda r: r.get("turn_saturation") or 0.0,
            default=None,
        )
        top_dir = _row_dir8(top_row) if top_row else None
        if top_dir is not None:
            return top_dir, None, f"{DIR8_LABELS[top_dir]}进口"

    return None, None, None
