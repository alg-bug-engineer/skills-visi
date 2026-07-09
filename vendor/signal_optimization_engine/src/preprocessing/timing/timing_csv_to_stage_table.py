#!/usr/bin/env python3
"""
配时方案转阶段工具：按 cycle_list 的 Ring-Barrier 结构解析「阶段」，
结合 greenTime/yellowTime/redTime（单相位放行时间=绿+黄+红）做多环同步时间线仿真。

支持两种输入输出方式：
  - CSV -> CSV
  - MySQL 源表 -> MySQL 新表（默认）

数据源为 signalctl 库 ODS 贴源表 ods_ctl_inter_scheme_hisense_raw（海信配时方案）：
  - 列名：cycle_json / phase_list_json / over_lap_phase_json（JSON 类型）；
    兼容旧表 signal_timing_d 的 cycle_list / phase_list / over_lap_phase_list 列名。
  - 主键为 (inter_id, plan_no, pattern_no)，无自增 id；按主键排序遍历；
    含 is_deleted 列时仅处理 is_deleted=0 的行。
  - 调度时段表 ods_ctl_inter_schedule_period_raw 不参与本脚本（阶段拆解仅依赖方案表）。

over_lap_phase_json（跟随/重叠相位，16 个槽位，与 phase_list 同构）：
  - includedPhases：bitmask，bit(k-1)=1 表示该跟随相位跟随母相位 k；
    任一母相位放行时跟随相位放行。
  - modifierPhases：修正相位 bitmask；判断基于当下并放的全部相位（跨 Ring 的
    并放集合，而非单相位）：并放集合命中 modifier 时该跟随相位被抑制不放行。
  - channelDim：跟随相位自身的进口转向，按相位 channelDim 同一套 8bit 编码解析。

阶段：在同一屏障段内各环并行；任一环当前相位结束时进入下一子区间；
屏障段依次衔接构成完整周期。跟随相位的流向并入其放行条件成立的各阶段描述。

母相位 channelDim 已混入其跟随相位的车流：解析母相位时按跟随相位的
included（母相位集合）剔除与跟随相位原子相同的流向，跟随车流仅经
跟随相位放行判定（included 命中且 modifier 未命中）并入阶段，避免
母相位被 modifier 抑制的时段仍出现跟随车流。

非有效机动车流过滤（仅影响阶段输出，不影响相位与方向的对应关系列）：
路口实际使用的相位（含跟随相位）中，若同一进口方向存在转向真包含
另一相位转向的机动车流（如 北左 与 北左掉、北直 与 北直左/北直掉/北直右
并存），仅在同源且无主辅路/厂商分流标签证据时剔除较长转向。`左掉`、
`直左`、`直掉`、纯 `掉` 等常用于区分不同物理车道簇，默认保留。
但若跟随相位的较长转向包含某个主相位车流，且该较长转向与自身母相位
车流直接冲突，则该跟随车流不是真正可随母相位放行的有效车流，应从
对应跟随相位中剔除。

输出（JSON 字符串列）：
  - 阶段方向描述：[[ "东直", "西左", "北行人" ], …] — 无环别；仅含可解析流向；
    同阶段内机动车（东直、西左等）在前，行人（…行人、入行、出行）在后。
  - 阶段时间：[秒数, …]（与上一数组逐元素对应）
  - 相位与方向的对应关系：{"1":"东直","2":"西左",…}，键为相位号字符串，值为该相位全部流向
    拼接（机动车在前、行人在后）；无解析结果的相位不出现在对象中。

相位中文标识：channelDim 解析同 ring_timing_visualizer。
无有效 channelDim 时解析 direction 文本；若 cycle_list 仅含一个 Cycle 且 channelDim 全为 0，
则 direction 按易华录 oad_direction（1–8 进口方位）+ flow_direction（含 20 行人）解析。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

try:
    import pymysql
    from pymysql.cursors import DictCursor, SSDictCursor
except ModuleNotFoundError:  # CSV 转换路径不需要 pymysql。
    pymysql = None
    DictCursor = None
    SSDictCursor = None

DEFAULT_SOURCE_TABLE = "ods_ctl_inter_scheme_hisense_raw"
DEFAULT_TARGET_TABLE = "ods_ctl_inter_scheme_hisense_stage"
TARGET_STAGE_DIRECTION_COLUMN = "stage_direction_desc"
TARGET_STAGE_TIME_COLUMN = "stage_time"
TARGET_PHASE_DIRECTION_MAP_COLUMN = "phase_direction_map"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 新 ODS 表与旧 signal_timing_d 表的列名对照（按顺序取首个存在的列）
CYCLE_COLUMN_ALIASES = ("cycle_json", "cycle_list")
PHASE_COLUMN_ALIASES = ("phase_list_json", "phase_list")
OVERLAP_COLUMN_ALIASES = ("over_lap_phase_json", "over_lap_phase_list")

DIRECTION_NAME = {
    0: "北",
    2: "东",
    4: "南",
    6: "西",
    1: "东北",
    3: "东南",
    5: "西南",
    7: "西北",
}
DIR8_NO_TO_DIRECTION_NAME = {
    0: "北",
    1: "东北",
    2: "东",
    3: "东南",
    4: "南",
    5: "西南",
    6: "西",
    7: "西北",
}
DIR8_NAME_TO_NO = {name: no for no, name in DIR8_NO_TO_DIRECTION_NAME.items()}

TURN_NAME = {
    -1: "未知",
    11: "直行",
    12: "左转",
    13: "右转",
    14: "直左调头",
    15: "右调头",
    16: "左右调头",
    17: "直右调头",
    18: "左直右调头",
    21: "直左混行",
    22: "直右混行",
    23: "左右混行",
    24: "直左右混行",
    31: "掉头",
    41: "直行掉头",
    42: "左转掉头",
    98: "其他",
    99: "其他",
    100: "出入口行人",
    101: "入口行人",
    102: "出口行人",
}

direction_map = {0: 0, 1: 2, 2: 4, 3: 6, 4: 1, 5: 3, 6: 5, 7: 7}
# channelDim 5bit 段解码用（与 ring_timing_visualizer 一致）
turn_map = {
    1: 12,
    2: 11,
    3: 13,
    4: 31,
    5: 42,
    6: 21,
    7: 23,
    8: 22,
    9: 24,
    10: 41,
    11: 101,
    12: 102,
    13: 100,
    14: 14,
    15: 15,
    16: 16,
    17: 17,
    18: 18,
}
# phase_list「direction」里「方向_转向」文本的第二段与 channelDim 的 5bit 索引（turn_map 1–18）
# 不是同一套枚举；未映射的整数会原样作为“转向码”，若无中文则显示为「码{n}」。
# 若掌握厂商/地方对照表，可在此增加：TEXT_FORMAT_TURN_MAP = {20: 11, ...} 再于 parse_direction_text 中引用。
TEXT_FORMAT_TURN_MAP: dict[int, int] = {}

TURN_SHORT: dict[int, str] = {
    11: "直",
    12: "左",
    13: "右",
    14: "直左掉",
    15: "右掉",
    16: "左右掉",
    17: "直右掉",
    18: "左直右掉",
    21: "直左",
    22: "直右",
    23: "左右",
    24: "直左右",
    31: "掉",
    41: "直掉",
    42: "左掉",
    98: "其他",
    99: "其他",
    100: "行人",
    101: "入行",
    102: "出行",
}

_PAIR_RE = re.compile(r"(\d+)_(\d+)")
_CYCLE_KEY_RE = re.compile(r"^Cycle(\d+)$", re.I)

# ---------------------------------------------------------------------------
# 易华录：单环 + channelDim 全 0 时，direction「方位_流向」文本（方位 1–8，流向见下表）
# ---------------------------------------------------------------------------
EHUALU_OAD_DIRECTION_CN: dict[int, str] = {
    1: "北",
    2: "东北",
    3: "东",
    4: "东南",
    5: "南",
    6: "西南",
    7: "西",
    8: "西北",
}
# flow_code -> (是否行人, 机动车时接在方位后的简称；行人由解析逻辑拼成「{方位}行人」)
EHUALU_FLOW_TO_CN: dict[int, tuple[bool, str]] = {
    1: (False, "左"),
    2: (False, "直"),
    3: (False, "右"),
    4: (False, "掉"),
    5: (False, "直左"),
    6: (False, "直右"),
    7: (False, "直左右"),
    8: (False, "左右"),
    9: (False, "左掉"),
    10: (False, "直掉"),
    11: (False, "右掉"),
    12: (False, "直左掉"),
    13: (False, "直右掉"),
    14: (False, "直左右掉"),
    15: (False, "左右掉"),
}

# 行人相关转向码（与 TURN_NAME 中出入口/入出口行人一致）
PEDESTRIAN_TURNS = frozenset({100, 101, 102})


def _is_pedestrian_turn(turn: int) -> bool:
    return turn in PEDESTRIAN_TURNS


def channelDim_analysis(channel_list: list) -> list:
    result = []
    for num in channel_list:
        if num == 0:
            result.append([])
        else:
            binary_num = bin(num)[2:]
            zero_count = (8 - len(binary_num) % 8) % 8
            binary_num = "0" * zero_count + binary_num
            binary_groups = [binary_num[i : i + 8] for i in range(0, len(binary_num), 8)]
            group_list = []
            for group in binary_groups:
                first_three = int(group[:3], 2)
                last_five = int(group[3:], 2)
                if last_five in turn_map:
                    direction = direction_map.get(first_three, first_three)
                    turn = turn_map[last_five]
                    group_list.append((direction, turn))
            result.append(group_list)
    return result


def _turn_to_short(turn_code: int) -> str:
    if turn_code in TURN_SHORT:
        return TURN_SHORT[turn_code]
    name = TURN_NAME.get(turn_code, "")
    if name:
        return name
    # 非 channelDim 标准内部码（如 direction 文本遗留的原始数）
    return f"码{turn_code}"


def _channels_to_atoms(channels: list[tuple[int, int]]) -> list[tuple[bool, str]]:
    """单相位内每条流向 -> (是否行人, 东直 / 北行人 等原子串)。"""
    atoms: list[tuple[bool, str]] = []
    for d, t in channels:
        dname = DIRECTION_NAME.get(d, f"D{d}")
        atoms.append((_is_pedestrian_turn(t), f"{dname}{_turn_to_short(t)}"))
    return atoms


def all_channel_dim_zero(phase_data: dict) -> bool:
    raw = phase_data.get("channelDim") or ""
    parts = str(raw).split()
    if not parts:
        return True
    try:
        return all(int(x) == 0 for x in parts)
    except ValueError:
        return False


def use_ehualu_direction_text(cycle_list_cell: str, phase_data: dict) -> bool:
    """单 Cycle 且 channelDim 全 0 时启用易华录 direction 解析。"""
    if not all_channel_dim_zero(phase_data):
        return False
    try:
        rings = parse_cycle_list_ordered(
            cycle_list_cell if cycle_list_cell and str(cycle_list_cell).strip() not in ("", "nan") else ""
        )
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        return False
    return len(rings) == 1


def parse_direction_text_ehualu(direction_str: str) -> list[tuple[bool, str]]:
    """
    易华录「方位_流向」：方位 1–8（oad_direction），流向 1–15 与 20（20 为行人）。
    返回与 _channels_to_atoms 相同结构的 (是否行人, 方位+流向简称)。
    """
    atoms: list[tuple[bool, str]] = []
    if not direction_str or not str(direction_str).strip():
        return atoms
    s = str(direction_str).strip()
    if s in ("0", "00"):
        return atoms
    if "_" not in s and "，" not in s:
        return atoms
    for m in _PAIR_RE.finditer(s.replace("，", ",")):
        oad = int(m.group(1))
        flow = int(m.group(2))
        if oad not in EHUALU_OAD_DIRECTION_CN:
            continue
        dcn = EHUALU_OAD_DIRECTION_CN[oad]
        if flow == 20:
            atoms.append((True, f"{dcn}行人"))
            continue
        if flow in EHUALU_FLOW_TO_CN:
            is_ped, suf = EHUALU_FLOW_TO_CN[flow]
            atoms.append((is_ped, f"{dcn}{suf}"))
        else:
            atoms.append((False, f"{dcn}码{flow}"))
    return atoms


def parse_direction_text(direction_str: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    if not direction_str or not str(direction_str).strip():
        return out
    s = str(direction_str).strip()
    if s in ("0", "00"):
        return out
    if "_" not in s and "，" not in s:
        return out
    for m in _PAIR_RE.finditer(s.replace("，", ",")):
        d_idx = int(m.group(1))
        raw_turn = int(m.group(2))
        if d_idx not in range(8):
            continue
        direction = d_idx
        if raw_turn in turn_map:
            turn = turn_map[raw_turn]
        elif raw_turn in TEXT_FORMAT_TURN_MAP:
            turn = TEXT_FORMAT_TURN_MAP[raw_turn]
        else:
            turn = raw_turn
        out.append((direction, turn))
    return out


def _normalize_json_cell(s: str) -> str:
    if not isinstance(s, str):
        return json.dumps(s, ensure_ascii=False)
    t = s.strip()
    t = t.replace("“", '"').replace("”", '"').replace('""', '"')
    t = t.replace("，", ",")
    return t


def parse_one_ring_string(ring_str: str) -> tuple[list[int], list[int]]:
    phases: list[int] = []
    barriers: list[int] = []
    parts = ring_str.replace("_", " _ ").split()
    phase_idx = 0
    for part in parts:
        if part == "_":
            if phases:
                barriers.append(phase_idx - 1)
        elif part.strip():
            phases.append(int(part.strip()))
            phase_idx += 1
    return phases, barriers


def parse_cycle_list_ordered(cycle_list_str: str) -> list[dict[str, list]]:
    if not cycle_list_str or str(cycle_list_str).strip() in ("", "nan"):
        return []
    s = _normalize_json_cell(str(cycle_list_str))
    cycle_dict = json.loads(s)
    keys = [k for k in cycle_dict if _CYCLE_KEY_RE.match(k)]
    keys.sort(key=lambda k: int(_CYCLE_KEY_RE.match(k).group(1)))
    rings = []
    for k in keys:
        p, b = parse_one_ring_string(str(cycle_dict[k]))
        rings.append({"phases": p, "barriers": b})
    return rings


def phases_to_barrier_segments(phases: list[int], barriers: list[int]) -> list[list[int]]:
    if not phases:
        return []
    barriers_sorted = sorted(set(int(x) for x in barriers))
    segments: list[list[int]] = []
    start = 0
    for b in barriers_sorted:
        segments.append(phases[start : b + 1])
        start = b + 1
    if start < len(phases):
        segments.append(phases[start:])
    return segments


def _pad_gyr(phase_data: dict) -> tuple[list[int], list[int], list[int]]:
    def split_ints(key: str) -> list[int]:
        raw = phase_data.get(key) or ""
        try:
            xs = [int(x) for x in str(raw).split()]
        except ValueError:
            xs = []
        while len(xs) < 16:
            xs.append(0)
        return xs[:16]

    return split_ints("greenTime"), split_ints("yellowTime"), split_ints("redTime")


def phase_total_duration(phase_no: int, g: list[int], y: list[int], r: list[int]) -> int:
    i = phase_no - 1
    if i < 0 or i >= 16:
        return 0
    return g[i] + y[i] + r[i]


def load_phase_data(phase_list_cell: str) -> dict | None:
    """从 CSV 的 phase_list 单元格解析出首条 phase 字典；失败返回 None。"""
    try:
        phase_list = json.loads(_normalize_json_cell(phase_list_cell))
    except (json.JSONDecodeError, TypeError):
        return None
    if not phase_list or not isinstance(phase_list, list):
        return None
    phase_data = phase_list[0]
    if not isinstance(phase_data, dict):
        return None
    return phase_data


@dataclass(frozen=True)
class OverlapPhase:
    """跟随（重叠）相位：跟随 included 中任一母相位放行，并放集合命中 modifier 时抑制。"""

    overlap_no: int  # 跟随相位槽位号（1 基）
    included: frozenset[int]  # 母相位号集合（1–16）
    modifier: frozenset[int]  # 修正相位号集合（1–16）
    atoms: list[tuple[bool, str]] = field(default_factory=list)  # 进口转向原子（同相位流向结构）

    def is_active(self, concurrent_phases: set[int]) -> bool:
        """concurrent_phases 为当下跨 Ring 并放的全部相位号集合。"""
        if not self.included & concurrent_phases:
            return False
        return not self.modifier & concurrent_phases


def _bitmask_to_phases(mask: int) -> frozenset[int]:
    """bitmask -> 相位号集合：bit(k-1) 对应相位 k（与 phase_list 的 concurrent 字段同约定）。"""
    return frozenset(k for k in range(1, 17) if mask >> (k - 1) & 1)


def load_overlap_phases(over_lap_cell: str) -> list[OverlapPhase]:
    """
    解析 over_lap_phase_json 单元格为有效跟随相位列表。

    单元格为单元素 JSON 数组，元素含 includedPhases / modifierPhases / channelDim
    三个 16 槽位空格分隔串；includedPhases 为 0 或 channelDim 解析不出流向的槽位忽略。
    """
    if _is_missing(over_lap_cell) or not str(over_lap_cell).strip():
        return []
    try:
        overlap_list = json.loads(_normalize_json_cell(str(over_lap_cell)))
    except (json.JSONDecodeError, TypeError):
        return []
    if not overlap_list or not isinstance(overlap_list, list):
        return []
    overlap_data = overlap_list[0]
    if not isinstance(overlap_data, dict):
        return []

    def split_ints(key: str) -> list[int]:
        try:
            xs = [int(x) for x in str(overlap_data.get(key) or "").split()]
        except ValueError:
            xs = []
        while len(xs) < 16:
            xs.append(0)
        return xs[:16]

    included_masks = split_ints("includedPhases")
    modifier_masks = split_ints("modifierPhases")
    channel_dims = split_ints("channelDim")
    channel_info = channelDim_analysis(channel_dims)

    overlaps: list[OverlapPhase] = []
    for i in range(16):
        included = _bitmask_to_phases(included_masks[i])
        atoms = _channels_to_atoms(channel_info[i])
        if not included or not atoms:
            continue
        overlaps.append(
            OverlapPhase(
                overlap_no=i + 1,
                included=included,
                modifier=_bitmask_to_phases(modifier_masks[i]),
                atoms=atoms,
            )
        )
    return overlaps


def _phase_atoms_to_label(atoms: list[tuple[bool, str]]) -> str:
    """单相位：机动车在前、行人在后，再拼接为一条描述。"""
    if not atoms:
        return ""
    triples = [(1 if ped else 0, atom) for ped, atom in atoms]
    triples.sort(key=lambda x: (x[0], x[1]))
    return "".join(t[1] for t in triples)


def _lane_has_left_capability(lane: dict[str, object]) -> bool:
    lane_type = lane.get("laneType")
    if lane_type not in (None, "", 0, "0"):
        return False
    try:
        drive_dir = int(lane.get("driveDir"))
    except (TypeError, ValueError):
        drive_dir = None
    if drive_dir is not None and drive_dir & 2:
        return True

    gb_code = str(lane.get("gbCode") or "")
    if gb_code in {"12", "21", "23", "24", "32"}:
        return True

    turns = {str(turn) for turn in lane.get("turns") or []}
    return bool(turns & {"left", "左"})


def _left_capable_dir_names(channelization: dict[str, object] | None) -> set[str]:
    """渠化中存在左转机动车车道的进口方位。"""
    if not channelization:
        return set()
    out: set[str] = set()
    for approach in channelization.get("approaches") or []:
        if not isinstance(approach, dict):
            continue
        try:
            dir8_no = int(approach.get("dir8No") or approach.get("dir8Code"))
        except (TypeError, ValueError):
            continue
        direction = DIR8_NO_TO_DIRECTION_NAME.get(dir8_no)
        if not direction:
            continue
        if any(
            isinstance(lane, dict) and _lane_has_left_capability(lane)
            for lane in approach.get("lanes") or []
        ):
            out.add(direction)
    return out


def _stage_has_motor_atom(stage_desc: list[str], direction: str, turn: str) -> bool:
    return any(
        (sp := _split_motor_atom(atom)) is not None
        and sp[0] == direction
        and turn in sp[1]
        for atom in stage_desc
    )


def _insert_motor_atom_after_through(stage_desc: list[str], direction: str, atom: str) -> list[str]:
    if atom in stage_desc:
        return stage_desc
    out = list(stage_desc)
    through_idx = next(
        (
            idx
            for idx, existing in enumerate(out)
            if (sp := _split_motor_atom(existing)) is not None
            and sp[0] == direction
            and "直" in sp[1]
        ),
        None,
    )
    if through_idx is not None:
        out.insert(through_idx + 1, atom)
        return out

    first_ped_idx = next(
        (idx for idx, existing in enumerate(out) if existing.endswith(("行人", "入行", "出行"))),
        len(out),
    )
    out.insert(first_ped_idx, atom)
    return out


def infer_left_follow_atoms_from_channelization(
    stage_dirs: list[list[str]],
    channelization: dict[str, object] | None,
) -> set[str]:
    """
    推断未在配时中显式体现、但可跟随同进口直行放行的左转车流。

    规则保守限定为：
    - 渠化中该进口存在左转机动车车道；
    - 全方案阶段描述中没有该进口任何含“左”的机动车原子；
    - 全方案阶段描述中存在该进口直行机动车原子，可作为跟随母流。
    """
    left_capable_dirs = _left_capable_dir_names(channelization)
    if not left_capable_dirs:
        return set()

    atoms = [atom for stage in stage_dirs for atom in stage]
    inferred: set[str] = set()
    for direction in sorted(left_capable_dirs, key=lambda name: DIR8_NAME_TO_NO.get(name, 99)):
        has_left_signal = any(
            (sp := _split_motor_atom(atom)) is not None
            and sp[0] == direction
            and "左" in sp[1]
            for atom in atoms
        )
        if has_left_signal:
            continue
        has_through_signal = any(
            (sp := _split_motor_atom(atom)) is not None
            and sp[0] == direction
            and "直" in sp[1]
            for atom in atoms
        )
        if has_through_signal:
            inferred.add(f"{direction}左")
    return inferred


def apply_left_follow_inference(
    stage_dirs: list[list[str]],
    channelization: dict[str, object] | None = None,
) -> list[list[str]]:
    """将“渠化有左转、配时无左转”的进口左转并入同进口直行阶段。"""
    inferred_atoms = infer_left_follow_atoms_from_channelization(stage_dirs, channelization)
    if not inferred_atoms:
        return stage_dirs

    out: list[list[str]] = []
    for stage_desc in stage_dirs:
        new_desc = list(stage_desc)
        for atom in sorted(inferred_atoms, key=lambda item: DIR8_NAME_TO_NO.get(_direction_prefix(item), 99)):
            direction = _direction_prefix(atom)
            if not _stage_has_motor_atom(new_desc, direction, "直"):
                continue
            if _stage_has_motor_atom(new_desc, direction, "左"):
                continue
            new_desc = _insert_motor_atom_after_through(new_desc, direction, atom)
        out.append(new_desc)
    return out


def build_phase_direction_map_json(
    phase_data: dict,
    cycle_list_cell: str = "",
    overlap_phases: list[OverlapPhase] | None = None,
) -> str:
    """
    相位号（字符串 \"1\"..\"16\"） -> 该相位方向中文描述。
    与阶段描述使用同一套 channelDim / direction 解析及机动车/行人排序。
    跟随相位以「跟随{n}」为键，标注其母相位号（included）及修正相位号（modifier，
    并放命中时抑制该跟随相位）。
    母相位 channelDim 中混入的跟随相位车流已剔除，仅保留在「跟随{n}」键下。
    """
    movements = build_phase_movements(phase_data, cycle_list_cell, overlap_phases)
    out: dict[str, str] = {}
    for i in range(16):
        label = _phase_atoms_to_label(movements[i])
        if label:
            out[str(i + 1)] = label
    for ov in overlap_phases or []:
        label = _phase_atoms_to_label(ov.atoms)
        if not label:
            continue
        included = ",".join(str(p) for p in sorted(ov.included))
        note = f"跟随相位{included}"
        if ov.modifier:
            modifier = ",".join(str(p) for p in sorted(ov.modifier))
            note += f";修正相位{modifier}"
        out[f"跟随{ov.overlap_no}"] = f"{label}({note})"
    return json.dumps(out, ensure_ascii=False)


def _strip_overlap_atoms(
    movements: list[list[tuple[bool, str]]],
    overlap_phases: list[OverlapPhase],
) -> list[list[tuple[bool, str]]]:
    """
    母相位 channelDim 中已混入其跟随相位的车流：对每个跟随相位，
    从其全部母相位（included）的流向原子中剔除与该跟随相位原子相同的项。
    剔除后跟随相位车流仅由阶段合成时按放行条件（included 命中且 modifier
    未命中）动态并入，避免母相位被抑制时段仍显示跟随车流。
    """
    if not overlap_phases:
        return movements
    out = [list(atoms) for atoms in movements]
    for ov in overlap_phases:
        ov_atoms = set(ov.atoms)
        if not ov_atoms:
            continue
        for p in ov.included:
            if 1 <= p <= 16:
                out[p - 1] = [a for a in out[p - 1] if a not in ov_atoms]
    return out


# 机动车基本转向（用于判断转向包含关系）
_ELEMENT_TURNS = frozenset("直左右掉")


def _split_motor_atom(atom: str) -> tuple[str, frozenset[str]] | None:
    """
    机动车原子拆为（进口方位, 基本转向集合）。
    转向部分必须全由 直/左/右/掉 组成（如 左掉、直左右），否则不可比较返回 None
    （行人原子、其他/码{n} 等均不参与包含判断）。
    """
    i = 0
    while i < len(atom) and atom[i] in "东南西北":
        i += 1
    direction, turn = atom[:i], atom[i:]
    if not direction or not turn:
        return None
    if any(c not in _ELEMENT_TURNS for c in turn):
        return None
    return direction, frozenset(turn)


VENDOR_TAG_SUFFIXES = ("直左掉", "左直右掉", "直左右掉", "左右掉", "左掉", "直掉", "直左")


def _is_vendor_lane_tag(atom: str) -> bool:
    sp = _split_motor_atom(atom)
    if not sp:
        return False
    _, turns = sp
    suffix = atom[len(_direction_prefix(atom)) :]
    return suffix in {"掉"} or suffix.endswith(VENDOR_TAG_SUFFIXES) or turns in (
        frozenset({"左", "掉"}),
        frozenset({"直", "掉"}),
        frozenset({"直", "左"}),
    )


def _direction_prefix(atom: str) -> str:
    i = 0
    while i < len(atom) and atom[i] in "东南西北":
        i += 1
    return atom[:i]


def _cross_source(short_sources: set[str], long_sources: set[str]) -> bool:
    if not short_sources or not long_sources:
        return False
    short_kinds = {src[:2] if src.startswith("OP") else src[:1] for src in short_sources}
    long_kinds = {src[:2] if src.startswith("OP") else src[:1] for src in long_sources}
    return short_sources.isdisjoint(long_sources) and short_kinds != long_kinds


def _collect_motor_atom_sources(
    movements: list[list[tuple[bool, str]]],
    overlap_phases: list[OverlapPhase],
    used_phases: set[int],
) -> dict[str, set[str]]:
    sources: dict[str, set[str]] = {}
    for ph in used_phases:
        if 1 <= ph <= 16:
            for is_ped, atom in movements[ph - 1]:
                if not is_ped:
                    sources.setdefault(atom, set()).add(f"P{ph}")
    for ov in overlap_phases:
        if ov.included & used_phases:
            for is_ped, atom in ov.atoms:
                if not is_ped:
                    sources.setdefault(atom, set()).add(f"OP{ov.overlap_no}")
    return sources


def _contained_motor_pairs(atom_strings: set[str]) -> list[tuple[str, str]]:
    parsed: dict[str, tuple[str, frozenset[str]]] = {}
    for atom in atom_strings:
        sp = _split_motor_atom(atom)
        if sp:
            parsed[atom] = sp
    pairs: list[tuple[str, str]] = []
    for long_atom, (dir_a, turns_a) in parsed.items():
        for short_atom, (dir_b, turns_b) in parsed.items():
            if long_atom != short_atom and dir_a == dir_b and turns_b < turns_a:
                pairs.append((short_atom, long_atom))
    return pairs


_DIR_INDEX_BY_NAME = {name: idx for idx, name in DIRECTION_NAME.items()}


def _motor_atom_contains(long_atom: str, short_atom: str) -> bool:
    long_sp = _split_motor_atom(long_atom)
    short_sp = _split_motor_atom(short_atom)
    if not long_sp or not short_sp:
        return False
    long_dir, long_turns = long_sp
    short_dir, short_turns = short_sp
    return long_dir == short_dir and short_turns < long_turns


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


def _motor_atoms_direct_conflict(atom_a: str, atom_b: str) -> bool:
    """
    粗粒度机动车流冲突判定，用于校验跟随相位是否能随母相位同时放行。
    同进口不视为直接冲突；对向左/掉与对向直/右、相交进口非双右转视为冲突。
    """
    sp_a = _split_motor_atom(atom_a)
    sp_b = _split_motor_atom(atom_b)
    if not sp_a or not sp_b:
        return False
    dir_a, turns_a = sp_a
    dir_b, turns_b = sp_b
    idx_a = _DIR_INDEX_BY_NAME.get(dir_a)
    idx_b = _DIR_INDEX_BY_NAME.get(dir_b)
    if idx_a is None or idx_b is None:
        return False
    dir_delta = (idx_b - idx_a) % 8
    return any(_motor_turns_conflict(ta, tb, dir_delta) for ta in turns_a for tb in turns_b)


def _find_conflicting_contained_overlap_atoms(
    movements: list[list[tuple[bool, str]]],
    overlap_phases: list[OverlapPhase],
    used_phases: set[int],
    parent_evidence_movements: list[list[tuple[bool, str]]] | None = None,
) -> dict[int, set[str]]:
    """
    找出应从跟随相位剔除的原子：
    - OP 原子是较长转向，包含任一主相位短转向；
    - 且该 OP 原子与其 included 母相位中的任一机动车流直接冲突。
    """
    main_atoms: set[str] = set()
    for ph in used_phases:
        if 1 <= ph <= 16:
            main_atoms |= {atom for is_ped, atom in movements[ph - 1] if not is_ped}
    if not main_atoms:
        return {}
    parent_movements = parent_evidence_movements or movements

    drops: dict[int, set[str]] = {}
    for ov in overlap_phases:
        if not ov.included & used_phases:
            continue
        # 带 modifier 的 OP 往往用修正相位表达工程上的分时保护；仅在无修正保护时，
        # 才把“与母相位直接冲突”作为强无效证据。
        if ov.modifier:
            continue
        parent_atoms: set[str] = set()
        for ph in ov.included & used_phases:
            if 1 <= ph <= 16:
                parent_atoms |= {atom for is_ped, atom in parent_movements[ph - 1] if not is_ped}
        if not parent_atoms:
            continue
        for is_ped, atom in ov.atoms:
            if is_ped:
                continue
            if not any(_motor_atom_contains(atom, main_atom) for main_atom in main_atoms):
                continue
            if any(_motor_atoms_direct_conflict(atom, parent_atom) for parent_atom in parent_atoms):
                drops.setdefault(ov.overlap_no, set()).add(atom)
    return drops


def _is_contained_overlap_atom(atom: str, phase_movements: list[list[tuple[bool, str]]]) -> bool:
    for atoms in phase_movements:
        for is_ped, main_atom in atoms:
            if not is_ped and _motor_atom_contains(atom, main_atom):
                return True
    return False


def _overlap_atom_conflicts_with_stage(
    atom: str,
    current_main_atoms: set[str],
    phase_movements: list[list[tuple[bool, str]]],
) -> bool:
    if not current_main_atoms or not _is_contained_overlap_atom(atom, phase_movements):
        return False
    return any(_motor_atoms_direct_conflict(atom, main_atom) for main_atom in current_main_atoms)


def _find_contained_motor_atoms(atom_strings: set[str]) -> set[str]:
    """
    在同一路口的全部机动车流原子中，找出「同进口方向且转向真包含另一原子转向」
    的原子（如同时存在 北左 与 北左掉 时，北左掉 被判为非有效车流）。
    返回应剔除的原子串集合。
    """
    return {long_atom for _, long_atom in _contained_motor_pairs(atom_strings)}


def _find_contained_motor_atoms_to_drop(
    atom_sources: dict[str, set[str]],
) -> set[str]:
    """
    带工程证据的 contained 剔除：
    - 长原子是厂商/主辅路分流标签时保留；
    - 短/长原子来自 P 与 OP 等不同控制来源时保留；
    - 其余同源 contained 才按历史逻辑剔除长原子。
    """
    contained: set[str] = set()
    for short_atom, long_atom in _contained_motor_pairs(set(atom_sources)):
        if _is_vendor_lane_tag(long_atom):
            continue
        if _cross_source(atom_sources.get(short_atom, set()), atom_sources.get(long_atom, set())):
            continue
        contained.add(long_atom)
    return contained


def _drop_contained_motor_flows(
    movements: list[list[tuple[bool, str]]],
    overlap_phases: list[OverlapPhase],
    used_phases: set[int],
    parent_evidence_movements: list[list[tuple[bool, str]]] | None = None,
) -> tuple[list[list[tuple[bool, str]]], list[OverlapPhase]]:
    """
    阶段合成前过滤非有效机动车流。contained 只作为候选条件，长原子若带厂商分流
    标签或与短原子 P/OP 分源，则保留，避免主辅路、多车道簇和跟随相位被误删。
    例外：OP 长原子若包含主相位短原子，但又与自身母相位机动车流直接冲突，
    则只从该 OP 中剔除，不影响主相位同名原子。
    """
    active_overlaps = [ov for ov in overlap_phases if ov.included & used_phases]
    overlap_atom_drops = _find_conflicting_contained_overlap_atoms(
        movements, active_overlaps, used_phases, parent_evidence_movements
    )
    atom_sources = _collect_motor_atom_sources(movements, active_overlaps, used_phases)
    contained = _find_contained_motor_atoms_to_drop(atom_sources)
    if not contained and not overlap_atom_drops:
        return movements, overlap_phases

    new_movements = [
        [(is_ped, atom) for is_ped, atom in atoms if is_ped or atom not in contained]
        for atoms in movements
    ]
    new_overlaps: list[OverlapPhase] = []
    for ov in overlap_phases:
        ov_drops = overlap_atom_drops.get(ov.overlap_no, set())
        kept = [
            (is_ped, atom)
            for is_ped, atom in ov.atoms
            if is_ped or (atom not in contained and atom not in ov_drops)
        ]
        if kept:
            new_overlaps.append(
                OverlapPhase(
                    overlap_no=ov.overlap_no,
                    included=ov.included,
                    modifier=ov.modifier,
                    atoms=kept,
                )
            )
    return new_movements, new_overlaps


def build_phase_movements(
    phase_data: dict,
    cycle_list_cell: str = "",
    overlap_phases: list[OverlapPhase] | None = None,
) -> list[list[tuple[bool, str]]]:
    """
    返回 16 个相位各自的流向原子列表。
    无 channelDim / direction 可解析时为空列表（该相位不参与阶段描述）。
    传入 overlap_phases 时，剔除母相位 channelDim 中混入的跟随相位车流
    （见 _strip_overlap_atoms）。
    """
    channel_str = phase_data.get("channelDim") or ""
    direction_strs = (phase_data.get("direction") or "").split()
    try:
        channel_dims = [int(x) for x in str(channel_str).split()]
    except ValueError:
        channel_dims = []
    while len(channel_dims) < 16:
        channel_dims.append(0)
    channel_dims = channel_dims[:16]
    channel_info = channelDim_analysis(channel_dims)
    ehualu = use_ehualu_direction_text(cycle_list_cell, phase_data)
    out: list[list[tuple[bool, str]]] = [[] for _ in range(16)]
    for i in range(16):
        ch = channel_info[i] if i < len(channel_info) else []
        if ch:
            out[i] = _channels_to_atoms(ch)
        elif i < len(direction_strs):
            text = direction_strs[i]
            if ehualu:
                atoms = parse_direction_text_ehualu(text)
                if atoms:
                    out[i] = atoms
            else:
                parsed = parse_direction_text(text)
                if parsed:
                    out[i] = _channels_to_atoms(parsed)
    return _strip_overlap_atoms(out, overlap_phases or [])


# 跟随相位原子在同组（机动车/行人）内排在所有环之后
_OVERLAP_RING_ORDER = 99


def _compose_stage_ordered_description(
    active_ring_indices: list[int],
    phase_no_per_ring: list[int],
    phase_movements: list[list[tuple[bool, str]]],
    overlap_phases: list[OverlapPhase] | None = None,
) -> list[str]:
    """
    合并多环当前相位上的所有原子流向：机动车在前、行人在后；
    同组内按环号再按字符串稳定排序。

    跟随相位：以当下并放相位集合（跨 Ring）判定 included 命中且 modifier 未命中时，
    其进口转向并入本阶段（同组内排在各环相位流向之后，去重）。若跟随车流是
    包含型长车流且与当前并放主相位车流直接冲突，则不并入当前阶段。
    """
    triples: list[tuple[int, int, str]] = []  # (sort_group, ring_idx, atom)
    concurrent_phases: set[int] = set()
    current_main_atoms: set[str] = set()
    for r in active_ring_indices:
        ph = phase_no_per_ring[r]
        if not (1 <= ph <= 16):
            continue
        concurrent_phases.add(ph)
        for is_ped, atom in phase_movements[ph - 1]:
            # 1=行人组在后，0=机动车组在前
            triples.append((1 if is_ped else 0, r, atom))
            if not is_ped:
                current_main_atoms.add(atom)
    if overlap_phases and concurrent_phases:
        existing = {t[2] for t in triples}
        for ov in overlap_phases:
            if not ov.is_active(concurrent_phases):
                continue
            for is_ped, atom in ov.atoms:
                if atom in existing:
                    continue
                if not is_ped and _overlap_atom_conflicts_with_stage(
                    atom, current_main_atoms, phase_movements
                ):
                    continue
                existing.add(atom)
                triples.append((1 if is_ped else 0, _OVERLAP_RING_ORDER, atom))
    triples.sort(key=lambda x: (x[0], x[1], x[2]))
    return [t[2] for t in triples]


def simulate_barrier_segment(
    segment_phases_per_ring: list[list[int]],
    duration_fn: Callable[[int], int],
    phase_movements: list[list[tuple[bool, str]]],
    overlap_phases: list[OverlapPhase] | None = None,
) -> tuple[list[list[str]], list[int]]:
    """单屏障窗内多环同步子阶段；方向为每阶段一条有序流向字符串数组。"""
    n = len(segment_phases_per_ring)
    ptr = [0] * n
    remain = [0] * n

    def load_remain(r: int) -> None:
        if ptr[r] < len(segment_phases_per_ring[r]):
            ph = segment_phases_per_ring[r][ptr[r]]
            remain[r] = duration_fn(ph)
        else:
            remain[r] = 0

    for r in range(n):
        load_remain(r)

    dir_stages: list[list[str]] = []
    time_stages: list[int] = []

    while any(ptr[r] < len(segment_phases_per_ring[r]) for r in range(n)):
        active = [r for r in range(n) if ptr[r] < len(segment_phases_per_ring[r])]
        if not active:
            break
        pos_rem = [remain[r] for r in active if remain[r] > 0]
        if not pos_rem:
            for r in active:
                if remain[r] <= 0:
                    ptr[r] += 1
                    load_remain(r)
            continue

        dt = min(pos_rem)
        if dt <= 0:
            for r in active:
                if remain[r] <= 0:
                    ptr[r] += 1
                    load_remain(r)
            continue

        phase_nos = [0] * n
        for r in active:
            if remain[r] > 0:
                phase_nos[r] = segment_phases_per_ring[r][ptr[r]]
        desc = _compose_stage_ordered_description(
            [r for r in active if remain[r] > 0],
            phase_nos,
            phase_movements,
            overlap_phases,
        )
        dir_stages.append(desc)
        time_stages.append(int(dt))

        for r in active:
            if remain[r] > 0:
                remain[r] -= dt
                if remain[r] <= 0:
                    ptr[r] += 1
                    load_remain(r)

    return dir_stages, time_stages


def build_stage_json_for_row(
    cycle_list_cell: str,
    phase_list_cell: str,
    over_lap_cell: str = "",
    channelization: dict[str, object] | None = None,
) -> tuple[str, str]:
    empty = "[]", "[]"
    phase_data = load_phase_data(phase_list_cell)
    if not phase_data:
        return empty

    g, y, r = _pad_gyr(phase_data)

    def dur(p: int) -> int:
        return phase_total_duration(p, g, y, r)

    cl_norm = cycle_list_cell if not _is_missing(cycle_list_cell) else ""
    overlap_phases = load_overlap_phases(over_lap_cell)
    parent_evidence_movements = build_phase_movements(phase_data, str(cl_norm))
    phase_movements = build_phase_movements(phase_data, str(cl_norm), overlap_phases)

    try:
        rings = parse_cycle_list_ordered(str(cl_norm))
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        return empty

    if not rings:
        return empty

    used_phases = {ph for ring in rings for ph in ring["phases"]}
    phase_movements, overlap_phases = _drop_contained_motor_flows(
        phase_movements,
        overlap_phases,
        used_phases,
        parent_evidence_movements=parent_evidence_movements,
    )

    segments_per_ring = [
        phases_to_barrier_segments(ring["phases"], ring["barriers"]) for ring in rings
    ]
    n_seg = min(len(s) for s in segments_per_ring) if segments_per_ring else 0

    all_dirs: list[list[str]] = []
    all_times: list[int] = []

    for si in range(n_seg):
        seg_rings = [segments_per_ring[ri][si] for ri in range(len(rings))]
        d_part, t_part = simulate_barrier_segment(seg_rings, dur, phase_movements, overlap_phases)
        all_dirs.extend(d_part)
        all_times.extend(t_part)

    all_dirs = apply_left_follow_inference(all_dirs, channelization)
    return json.dumps(all_dirs, ensure_ascii=False), json.dumps(all_times, ensure_ascii=False)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    return False


def _normalize_cell_value(value: object) -> str:
    if _is_missing(value):
        return ""
    return str(value)


def _resolve_column(fieldnames: list[str] | set[str], aliases: tuple[str, ...]) -> str | None:
    for name in aliases:
        if name in fieldnames:
            return name
    return None


def convert_csv(input_path: Path, output_path: Path) -> None:
    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    phase_col = _resolve_column(fieldnames, PHASE_COLUMN_ALIASES)
    cycle_col = _resolve_column(fieldnames, CYCLE_COLUMN_ALIASES)
    overlap_col = _resolve_column(fieldnames, OVERLAP_COLUMN_ALIASES)
    if not phase_col:
        raise ValueError(f"CSV 缺少相位列（{' / '.join(PHASE_COLUMN_ALIASES)}）")
    if not cycle_col:
        raise ValueError(f"CSV 缺少环结构列（{' / '.join(CYCLE_COLUMN_ALIASES)}）")

    output_fieldnames = fieldnames + [
        name
        for name in ("相位与方向的对应关系", "阶段方向描述", "阶段时间")
        if name not in fieldnames
    ]

    for row in rows:
        pl = _normalize_cell_value(row.get(phase_col, ""))
        cl = _normalize_cell_value(row.get(cycle_col, ""))
        ol = _normalize_cell_value(row.get(overlap_col, "")) if overlap_col else ""
        pd_obj = load_phase_data(pl)
        overlaps = load_overlap_phases(ol)
        row["相位与方向的对应关系"] = (
            build_phase_direction_map_json(pd_obj, cl, overlaps) if pd_obj else "{}"
        )
        dj, tj = build_stage_json_for_row(cl, pl, ol)
        row["阶段方向描述"] = dj
        row["阶段时间"] = tj

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _quote_identifier(name: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(name):
        raise ValueError(f"非法标识符: {name}")
    return f"`{name}`"


def _parse_mysql_url(mysql_url: str) -> dict[str, object]:
    parsed = urlparse(mysql_url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise ValueError("MYSQL_URL 仅支持 mysql:// 或 mysql+pymysql://")
    database = parsed.path.lstrip("/")
    if not database:
        raise ValueError("MYSQL_URL 缺少数据库名")
    query = parse_qs(parsed.query)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": database,
        "charset": query.get("charset", ["utf8mb4"])[0],
    }


def _get_mysql_connection(*, streaming: bool = False) -> pymysql.connections.Connection:
    if pymysql is None:
        raise ModuleNotFoundError("MySQL 转换模式需要安装 pymysql")

    mysql_url = os.getenv("MYSQL_URL", "")
    if not mysql_url:
        raise ValueError("未配置 MYSQL_URL")
    conn_args = _parse_mysql_url(mysql_url)
    conn_args["cursorclass"] = SSDictCursor if streaming else DictCursor
    conn_args["autocommit"] = False
    return pymysql.connect(**conn_args)


def _column_exists(conn: pymysql.connections.Connection, table_name: str, column_name: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM {_quote_identifier(table_name)} LIKE %s", (column_name,))
        return cursor.fetchone() is not None


def _resolve_order_by_clause(conn: pymysql.connections.Connection, table_name: str) -> str:
    """优先按自增 id 排序（旧表）；否则按主键列排序（新 ODS 表无 id 列）。"""
    if _column_exists(conn, table_name, "id"):
        return "ORDER BY `id`"
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW KEYS FROM {_quote_identifier(table_name)} WHERE Key_name = 'PRIMARY'")
        rows = cursor.fetchall() or []
    key_rows = sorted(rows, key=lambda r: int(r["Seq_in_index"]))
    if not key_rows:
        return ""
    columns = ", ".join(_quote_identifier(r["Column_name"]) for r in key_rows)
    return f"ORDER BY {columns}"


def ensure_target_table(
    conn: pymysql.connections.Connection,
    source_table: str,
    target_table: str,
    *,
    replace_target: bool = False,
) -> None:
    if source_table == target_table:
        raise ValueError("目标表必须与源表不同")
    with conn.cursor() as cursor:
        if replace_target:
            cursor.execute(f"DROP TABLE IF EXISTS {_quote_identifier(target_table)}")
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {_quote_identifier(target_table)} "
            f"LIKE {_quote_identifier(source_table)}"
        )
    conn.commit()

    extra_columns = {
        TARGET_PHASE_DIRECTION_MAP_COLUMN: "LONGTEXT NULL COMMENT '相位号与方向描述映射(JSON)'",
        TARGET_STAGE_DIRECTION_COLUMN: "LONGTEXT NULL COMMENT '阶段方向描述(JSON数组)'",
        TARGET_STAGE_TIME_COLUMN: "LONGTEXT NULL COMMENT '阶段时间(JSON数组)'",
    }
    for column_name, definition in extra_columns.items():
        if _column_exists(conn, target_table, column_name):
            continue
        with conn.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE {_quote_identifier(target_table)} "
                f"ADD COLUMN {_quote_identifier(column_name)} {definition}"
            )
        conn.commit()


def _transform_row(row: dict[str, object]) -> dict[str, object]:
    result = dict(row)
    keys = set(result)
    phase_col = _resolve_column(keys, PHASE_COLUMN_ALIASES)
    cycle_col = _resolve_column(keys, CYCLE_COLUMN_ALIASES)
    overlap_col = _resolve_column(keys, OVERLAP_COLUMN_ALIASES)
    phase_list_cell = _normalize_cell_value(result.get(phase_col, "")) if phase_col else ""
    cycle_list_cell = _normalize_cell_value(result.get(cycle_col, "")) if cycle_col else ""
    overlap_cell = _normalize_cell_value(result.get(overlap_col, "")) if overlap_col else ""
    phase_data = load_phase_data(phase_list_cell)
    overlaps = load_overlap_phases(overlap_cell)
    result[TARGET_PHASE_DIRECTION_MAP_COLUMN] = (
        build_phase_direction_map_json(phase_data, cycle_list_cell, overlaps)
        if phase_data
        else "{}"
    )
    stage_direction_json, stage_time_json = build_stage_json_for_row(
        cycle_list_cell, phase_list_cell, overlap_cell
    )
    result[TARGET_STAGE_DIRECTION_COLUMN] = stage_direction_json
    result[TARGET_STAGE_TIME_COLUMN] = stage_time_json
    return result


def _build_upsert_sql(table_name: str, columns: list[str]) -> str:
    quoted_columns = ", ".join(_quote_identifier(col) for col in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    update_columns = [col for col in columns if col != "id"]
    if not update_columns:
        raise ValueError("写入列不能为空")
    update_clause = ", ".join(
        f"{_quote_identifier(col)}=VALUES({_quote_identifier(col)})" for col in update_columns
    )
    return (
        f"INSERT INTO {_quote_identifier(table_name)} ({quoted_columns}) "
        f"VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )


def _upsert_rows(
    conn: pymysql.connections.Connection,
    table_name: str,
    rows: list[dict[str, object]],
) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    values = [tuple(row.get(col) for col in columns) for row in rows]
    sql = _build_upsert_sql(table_name, columns)
    with conn.cursor() as cursor:
        cursor.executemany(sql, values)
    conn.commit()


def convert_mysql_table(
    source_table: str = DEFAULT_SOURCE_TABLE,
    target_table: str = DEFAULT_TARGET_TABLE,
    *,
    batch_size: int = 500,
    replace_target: bool = False,
) -> int:
    source_ident = _quote_identifier(source_table)
    processed = 0
    read_conn = _get_mysql_connection(streaming=True)
    write_conn = _get_mysql_connection(streaming=False)
    try:
        ensure_target_table(
            write_conn,
            source_table=source_table,
            target_table=target_table,
            replace_target=replace_target,
        )
        where_clause = (
            "WHERE `is_deleted` = 0" if _column_exists(write_conn, source_table, "is_deleted") else ""
        )
        order_by_clause = _resolve_order_by_clause(write_conn, source_table)
        query = " ".join(
            part for part in (f"SELECT * FROM {source_ident}", where_clause, order_by_clause) if part
        )
        with read_conn.cursor() as cursor:
            cursor.execute(query)
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                transformed_rows = [_transform_row(row) for row in rows]
                _upsert_rows(write_conn, target_table, transformed_rows)
                processed += len(transformed_rows)
                print(f"已处理 {processed} 条")
    finally:
        read_conn.close()
        write_conn.close()
    return processed


def main() -> None:
    from env import load_project_env

    load_project_env()
    p = argparse.ArgumentParser(description="配时表转阶段结果，支持 CSV 与 MySQL 落表")
    p.add_argument("-i", "--input", type=Path, help="CSV 输入文件；传入后启用 CSV 模式")
    p.add_argument("-o", "--output", type=Path, help="CSV 输出文件；CSV 模式下默认自动推导")
    p.add_argument("--source-table", default=DEFAULT_SOURCE_TABLE, help="MySQL 源表名")
    p.add_argument("--target-table", default=DEFAULT_TARGET_TABLE, help="MySQL 目标表名")
    p.add_argument("--batch-size", type=int, default=500, help="MySQL 批量写入大小")
    p.add_argument(
        "--replace-target",
        action="store_true",
        help="重建目标表（先删后建），适合全量重跑",
    )
    args = p.parse_args()
    if args.input:
        output_path = args.output or args.input.with_name(f"{args.input.stem}_阶段表{args.input.suffix}")
        convert_csv(args.input, output_path)
        print(f"已写入 CSV: {output_path}")
        return

    processed = convert_mysql_table(
        source_table=args.source_table,
        target_table=args.target_table,
        batch_size=args.batch_size,
        replace_target=args.replace_target,
    )
    print(f"已写入数据表: {args.target_table}，共 {processed} 条")


if __name__ == "__main__":
    main()
