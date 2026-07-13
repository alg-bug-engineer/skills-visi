"""Topology helpers adapted from references/流量溯源."""

from __future__ import annotations

from app.data.ticket_nlu_schema import normalize_travel_direction

DIR8_ENTRY = {
    0: "北进口",
    1: "东北进口",
    2: "东进口",
    3: "东南进口",
    4: "南进口",
    5: "西南进口",
    6: "西进口",
    7: "西北进口",
}

TURN_LABEL = {1: "左转", 2: "直行", 3: "右转", 4: "掉头"}

DIRECTION_MOVEMENT = {
    "东向西": (2, 2),
    "西向东": (6, 2),
    "南向北": (4, 2),
    "北向南": (0, 2),
    "东北向西南": (1, 2),
    "东南向西北": (3, 2),
    "西南向东北": (5, 2),
    "西北向东南": (7, 2),
}

EN_DIRECTION_MOVEMENT = {
    "east_to_west": (2, 2),
    "west_to_east": (6, 2),
    "south_to_north": (4, 2),
    "north_to_south": (0, 2),
    "northeast_to_southwest": (1, 2),
    "southeast_to_northwest": (3, 2),
    "southwest_to_northeast": (5, 2),
    "northwest_to_southeast": (7, 2),
}


def exit_dir8_for_turn(entrance_dir8: int, turn: int) -> int | None:
    try:
        d = int(entrance_dir8)
        t = int(turn)
    except (TypeError, ValueError):
        return None
    if t == 2:
        return (d + 4) % 8
    if t == 1:
        return (d + 2) % 8
    if t == 3:
        return (d + 6) % 8
    if t == 4:
        return d
    return None


def movement_label(dir8: int | None, turn: int | None) -> str:
    entry = DIR8_ENTRY.get(int(dir8) if dir8 is not None else -1, "")
    turn_cn = TURN_LABEL.get(int(turn) if turn is not None else -1, "")
    return f"{entry}{turn_cn}" if entry and turn_cn else (entry or turn_cn or "")


def resolve_dir8_turn(direction: str, movement: str = "直行") -> tuple[int, int]:
    raw_direction = normalize_travel_direction(direction)
    raw_movement = str(movement or "").strip().lower()
    turn_map = {
        "左转": 1,
        "left": 1,
        "left_turn": 1,
        "直行": 2,
        "straight": 2,
        "through": 2,
        "右转": 3,
        "right": 3,
        "right_turn": 3,
        "掉头": 4,
        "uturn": 4,
        "u_turn": 4,
    }
    turn = turn_map.get(raw_movement, 2)
    normalized_direction = raw_direction.lower().replace("-", "_").replace(" ", "_")
    if normalized_direction in EN_DIRECTION_MOVEMENT:
        return EN_DIRECTION_MOVEMENT[normalized_direction][0], turn
    if raw_direction in DIRECTION_MOVEMENT:
        return DIRECTION_MOVEMENT[raw_direction][0], turn
    # 用户和筛选结果常直接使用“北进口/西进口”等进口名称；此前这些值
    # 会落入最终的东进口兜底，导致峰值查询静默查错方向。
    for dir8, entry_label in DIR8_ENTRY.items():
        if raw_direction == entry_label:
            return dir8, turn
    for label, pair in DIRECTION_MOVEMENT.items():
        if raw_direction in label or label in raw_direction:
            return pair[0], turn
    return 2, turn
