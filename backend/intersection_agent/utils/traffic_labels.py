"""Traffic direction / turn labels for diagnosis narrative."""

from __future__ import annotations

DIR8_LABELS: dict[int, str] = {
    0: "北",
    1: "东北",
    2: "东",
    3: "东南",
    4: "南",
    5: "西南",
    6: "西",
    7: "西北",
}

TURN_DIR_LABELS: dict[int, str] = {
    0: "掉头",
    1: "左转",
    2: "直行",
    3: "右转",
}

LOS_LABELS: dict[str, str] = {
    "A": "A-畅通",
    "B": "B-稳定",
    "C": "C-较稳",
    "D": "D-临界",
    "E": "E-拥堵",
    "F": "F-阻塞",
}


def turn_label(dir8_code: int | None, turn_dir_no: int | None) -> str:
    """Human-readable turn movement label."""
    dir_part = DIR8_LABELS.get(int(dir8_code or 0), "—")
    turn_part = TURN_DIR_LABELS.get(int(turn_dir_no or 2), "直行")
    return f"{dir_part}{turn_part}"
