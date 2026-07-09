"""路口进口 link 状态指标核心计算逻辑（纯函数，便于单测）。"""

from __future__ import annotations

from typing import Any

MAIN_TURN_STRAIGHT = 2
MAIN_TURN_LEFT = 1
MAIN_DIRECTION_FLOW_RATIO = 1.5
MIN_RED_SEC = 20
VEHICLE_HEADWAY_M = 6.5
LINK_INDEX_2MIN_STEP_COUNT = 720
LINK_INDEX_5MIN_STEP_COUNT = 288

# dwd_tfc_link_index_2mi 实际字段映射
LINK_INDEX_SOURCE_FIELDS = {
    "delay_index": "avg_jam_delay_index",
    "stop_time_sec": "delay_dur",
    "avg_speed_kmh": "avg_speed",
    "avg_nostop_speed": "avg_nostop_speed",
    "day_of_week": "week_day",
}

# turn_move 国标码含义（GB/T 相关口径，与 pg_reader.GB_LABELS 一致）
GB_TURN_MOVE_LABELS: dict[int, str] = {
    11: "直行",
    12: "左转",
    13: "右转",
    21: "直左混行",
    22: "直右混行",
    23: "左右混行",
    24: "直左右混行",
    31: "掉头",
    32: "掉头加左转",
    33: "掉头加直行",
    34: "掉头加右转",
    40: "公交专用道",
    41: "可变车道",
    42: "潮汐车道",
    99: "无限制/空",
}

# 国标码 → 聚合转向编号（1=左转/掉头，2=直行，3=右转）；混行码计入多个桶
_TURN_MOVE_DIR_MAP: dict[int, tuple[int, ...]] = {
    11: (2,),
    12: (1,),
    13: (3,),
    21: (1, 2),
    22: (2, 3),
    23: (1, 3),
    24: (1, 2, 3),
    31: (1,),
    32: (1,),
    33: (1, 2),
    34: (1, 3),
}

# 40/41/42/99 等特殊车道码不参与转向流量聚合
TURN_MOVE_EXCLUDED = frozenset({40, 41, 42, 99})

TURN_MOVE_LEFT = frozenset(code for code, dirs in _TURN_MOVE_DIR_MAP.items() if 1 in dirs)
TURN_MOVE_STRAIGHT = frozenset(code for code, dirs in _TURN_MOVE_DIR_MAP.items() if 2 in dirs)
TURN_MOVE_RIGHT = frozenset(code for code, dirs in _TURN_MOVE_DIR_MAP.items() if 3 in dirs)


def link_index_step_5min(step_index_2min: int) -> int:
    """2 分钟 step_index(0..719) → 5 分钟 step_index(0..287)。"""
    return max(0, min(LINK_INDEX_5MIN_STEP_COUNT - 1, (int(step_index_2min) * 2) // 5))


def turn_move_in_sql(codes: frozenset[int]) -> str:
    return ", ".join(str(code) for code in sorted(codes))


def turn_move_maps_to_dir(turn_move: int, turn_dir_no: int) -> bool:
    """判断国标 turn_move 是否应计入指定 turn_dir_no 聚合桶。"""
    dirs = _TURN_MOVE_DIR_MAP.get(int(turn_move))
    return dirs is not None and int(turn_dir_no) in dirs


def select_main_entrance_links(
    rows: list[dict[str, Any]],
    *,
    inter_id_key: str = "inter_id",
    link_id_key: str = "link_id",
    dir8_code_key: str = "dir8_code",
    lane_num_key: str = "lane_num",
) -> list[dict[str, Any]]:
    """同一进口方向（dir8_code）有多条 link 时，取 lane_num 最大的主路 link 代表该方向。"""
    best: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        inter_id = str(row.get(inter_id_key) or "")
        link_id = str(row.get(link_id_key) or "")
        dir8_raw = row.get(dir8_code_key)
        if not inter_id or not link_id or dir8_raw is None:
            continue
        dir8_code = int(dir8_raw)
        lane_num = int(row.get(lane_num_key) or 0)
        key = (inter_id, dir8_code)
        current = best.get(key)
        if current is None or lane_num > int(current.get(lane_num_key) or 0):
            best[key] = {**row, lane_num_key: lane_num}
            continue
        if lane_num == int(current.get(lane_num_key) or 0) and link_id < str(current.get(link_id_key) or ""):
            best[key] = {**row, lane_num_key: lane_num}
    return list(best.values())


def entrance_links_cte_sql(*, channel_q: str, inter_clause: str = "") -> str:
    """生成 entrance_links CTE：每进口方向仅保留 lane_num 最大的主路 link。"""
    return f"""
entrance_candidates AS (
    SELECT
        ch.inter_id::text AS inter_id,
        ch.link_id::text AS link_id,
        NULLIF(ch.dir8_code::text, '')::smallint AS dir8_code,
        COALESCE(NULLIF(ch.lane_num::text, '')::int, 0) AS lane_num
    FROM {channel_q} ch
    WHERE lower(btrim(ch.link_role::text)) = 'entrance'
      AND ch.link_id IS NOT NULL
      AND btrim(ch.link_id::text) <> ''
      {inter_clause}
),
entrance_links AS (
    SELECT inter_id, link_id, dir8_code
    FROM (
        SELECT
            inter_id,
            link_id,
            dir8_code,
            ROW_NUMBER() OVER (
                PARTITION BY inter_id, dir8_code
                ORDER BY lane_num DESC, link_id
            ) AS rn
        FROM entrance_candidates
    ) ranked
    WHERE rn = 1
)""".strip()


def select_main_turn_dirs(straight_flow: float, left_flow: float) -> list[int]:
    """判定 link 主方向：直行(2) vs 左转(1) 流量对比。

    若一方流量大于另一方 50%（即 > 1.5 倍），则流量较大者为主方向；
    否则直行与左转均为主方向。
    """
    straight = max(float(straight_flow or 0), 0.0)
    left = max(float(left_flow or 0), 0.0)
    if straight > left * MAIN_DIRECTION_FLOW_RATIO:
        return [MAIN_TURN_STRAIGHT]
    if left > straight * MAIN_DIRECTION_FLOW_RATIO:
        return [MAIN_TURN_LEFT]
    return [MAIN_TURN_LEFT, MAIN_TURN_STRAIGHT]


def avg_red_sec_for_main_turns(
    timing_by_turn: dict[int, float | None],
    main_turns: list[int],
    *,
    weights: dict[int, float] | None = None,
) -> float | None:
    """主方向平均红灯时长（秒）。红灯 = cycle_len_sec - green_exec_sec。"""
    values: list[tuple[float, float]] = []
    for turn in main_turns:
        red = timing_by_turn.get(turn)
        if red is None or red <= 0:
            continue
        weight = 1.0
        if weights is not None:
            weight = max(float(weights.get(turn, 0) or 0), 0.0)
            if weight <= 0:
                continue
        values.append((float(red), weight))
    if not values:
        return None
    total_weight = sum(weight for _, weight in values)
    if total_weight <= 0:
        return None
    return sum(value * weight for value, weight in values) / total_weight


def avg_lane_flow_for_main_turns(
    flow_by_turn: dict[int, float | None],
    main_turns: list[int],
) -> float | None:
    """主方向平均车道级 5 分钟流量（辆/5min/车道）。"""
    samples = [
        float(flow_by_turn[turn])
        for turn in main_turns
        if flow_by_turn.get(turn) is not None and float(flow_by_turn[turn]) >= 0
    ]
    if not samples:
        return None
    return sum(samples) / len(samples)


def calc_travel_time_sec(link_length_m: float, avg_speed_kmh: float) -> float | None:
    """行程时间（秒）= link 长度 / 行程车速。"""
    length = float(link_length_m or 0)
    speed = float(avg_speed_kmh or 0)
    if length <= 0 or speed <= 0:
        return None
    return length / (speed / 3.6)


def calc_stop_times(stop_time_sec: float, avg_red_sec: float) -> float | None:
    """平均停车次数 = 延误时间 / 主方向平均红灯时长。"""
    delay = float(stop_time_sec or 0)
    red = float(avg_red_sec or 0)
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
    """排队长度估计（米）= min(平均停车次数 × 平均车道流量 × 6.5, link 长度)。"""
    stops = float(stop_times or 0)
    flow = float(avg_lane_flow or 0)
    length = float(link_length_m or 0)
    if stops < 0 or flow < 0 or length <= 0:
        return None
    return min(stops * flow * headway_m, length)


def should_skip_timing(avg_red_sec: float | None, has_timing: bool) -> bool:
    """无配时或红灯时长 < 20 秒时不计算指标。"""
    if not has_timing or avg_red_sec is None:
        return True
    return avg_red_sec < MIN_RED_SEC


def format_main_turn_dirs(main_turns: list[int]) -> str:
    return ",".join(str(turn) for turn in sorted(set(main_turns)))
