#!/usr/bin/env python3
"""
将海信配时方案 CSV 和路口配时方案计划 CSV 拆解为路口信控标准表 CSV。

默认读取当前目录下：
  - 配时方案.csv
  - 路口配时方案计划表.csv

默认输出到当前目录 standard_tables/，每个标准表一个 CSV。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from preprocessing.timing.timing_csv_to_stage_table import (
    CYCLE_COLUMN_ALIASES,
    OVERLAP_COLUMN_ALIASES,
    PHASE_COLUMN_ALIASES,
    OverlapPhase,
    apply_left_follow_inference,
    _compose_stage_ordered_description,
    _drop_contained_motor_flows,
    _get_mysql_connection,
    _quote_identifier,
    build_phase_movements,
    infer_left_follow_atoms_from_channelization,
    load_overlap_phases,
    load_phase_data,
    parse_cycle_list_ordered,
    phases_to_barrier_segments,
)
from preprocessing.timing.atom_lane_mapping import (
    mapping_summary,
    movement_key_for_atom,
    parse_signal_atom,
)

DEFAULT_SCHEME_TABLE = "ods_ctl_inter_scheme_hisense_raw"
DEFAULT_SCHEDULE_TABLE = "ods_ctl_inter_schedule_period_raw"

# 新 ODS 表与旧 CSV 的标量列名对照（按顺序取首个存在的列）
PATTERN_COLUMN_ALIASES = ("pattern_no", "pattern")
CYCLE_LEN_COLUMN_ALIASES = ("cycle_len_sec", "cycle_len")
OFFSET_COLUMN_ALIASES = ("offset_sec", "offset")
INTER_NAME_COLUMN_ALIASES = ("inter_name", "海信name")

TABLE_STAGE_CFG = "dwd_ctl_inter_stage_cfg"
TABLE_STAGE_MOTOR_FLOW = "dwd_ctl_inter_stage_motor_flow_rltn"
TABLE_PLAN_CFG = "dwd_ctl_inter_plan_cfg"
TABLE_PLAN_STAGE_TIMING = "dwd_ctl_inter_plan_stage_timing"
TABLE_PLAN_STAGE_PHASE_RLTN = "dwd_ctl_inter_plan_stage_phase_rltn"
TABLE_DAY_PLAN_CFG = "dwd_ctl_inter_day_plan_cfg"
TABLE_DAY_PLAN_PERIOD = "dwd_ctl_inter_day_plan_period"
TABLE_SCHEDULE_CFG = "dwd_ctl_inter_schedule_cfg"
TABLE_ATOM_LANE_MAPPING = "dwd_ctl_inter_signal_atom_lane_mapping"
TABLE_QUALITY_ISSUE = "dwd_ctl_inter_timing_parse_quality_issue"

SOURCE_SYSTEM = "HISENSE"
SOURCE_PROTOCOL = "VENDOR_PRIVATE"
VENDOR_CODE = "HISENSE"
CTRL_MODE_TIMING = "21"
CTRL_MODE_COORD_TIMING = "31"

COMMON_COLUMNS = [
    "create_time",
    "update_time",
    "is_deleted",
]

TABLE_COLUMNS = {
    TABLE_STAGE_CFG: [
        "inter_id",
        "cross_id",
        "signal_controller_id",
        "stage_no",
        "stage_name",
        "flow_combo_json",
        "remark",
    ]
    + COMMON_COLUMNS,
    TABLE_STAGE_MOTOR_FLOW: [
        "inter_id",
        "cross_id",
        "stage_no",
        "flow_seq_no",
        "from_link_id",
        "f_dir8_no",
        "flow_type_no",
        "flow_type_name",
        "lane_id_list",
        "remark",
    ]
    + COMMON_COLUMNS,
    TABLE_PLAN_CFG: [
        "inter_id",
        "cross_id",
        "signal_controller_id",
        "plan_no",
        "plan_name",
        "cycle_len_sec",
        "coord_stage_no",
        "offset_sec",
        "stage_cnt",
        "plan_source_no",
        "schema_version",
        "signal_atom_json",
        "movement_mapping_json",
        "parse_quality_json",
        "remark",
    ]
    + COMMON_COLUMNS,
    TABLE_PLAN_STAGE_TIMING: [
        "inter_id",
        "cross_id",
        "plan_no",
        "stage_seq_no",
        "stage_no",
        "green_sec",
        "yellow_sec",
        "all_red_sec",
        "max_green_sec",
        "min_green_sec",
        "stage_total_sec",
        "adjust_json",
        "remark",
    ]
    + COMMON_COLUMNS,
    TABLE_PLAN_STAGE_PHASE_RLTN: [
        "inter_id",
        "cross_id",
        "plan_no",
        "stage_seq_no",
        "stage_no",
        "source_type",
        "source_no",
        "source_key",
        "ring_no",
        "barrier_seq_no",
        "phase_seq_no",
        "is_active_green",
        "included_phase_nos_json",
        "modifier_phase_nos_json",
        "evidence_json",
        "remark",
    ]
    + COMMON_COLUMNS,
    TABLE_DAY_PLAN_CFG: [
        "inter_id",
        "cross_id",
        "signal_controller_id",
        "day_plan_no",
        "day_plan_name",
        "period_cnt",
        "remark",
    ]
    + COMMON_COLUMNS,
    TABLE_DAY_PLAN_PERIOD: [
        "inter_id",
        "cross_id",
        "day_plan_no",
        "period_seq_no",
        "start_time",
        "end_time",
        "plan_no",
        "ctrl_mode",
        "action_json",
        "remark",
    ]
    + COMMON_COLUMNS,
    TABLE_SCHEDULE_CFG: [
        "inter_id",
        "cross_id",
        "signal_controller_id",
        "schedule_no",
        "schedule_name",
        "schedule_type_no",
        "priority_no",
        "start_day",
        "end_day",
        "week_day_no",
        "day_plan_no",
        "remark",
    ]
    + COMMON_COLUMNS,
    TABLE_ATOM_LANE_MAPPING: [
        "inter_id",
        "cross_id",
        "plan_no",
        "stage_no",
        "signal_atom",
        "source_key",
        "source_type",
        "vendor_tag",
        "dir8_no",
        "turn_dir_no",
        "link_id",
        "lane_group_id",
        "lane_nos_json",
        "cluster_kind",
        "capabilities_json",
        "movement_key",
        "confidence",
        "score",
        "evidence_json",
        "flow_green_check_json",
        "schema_version",
    ]
    + COMMON_COLUMNS,
    TABLE_QUALITY_ISSUE: [
        "issue_type",
        "inter_id",
        "cross_id",
        "plan_no",
        "day_plan_no",
        "stage_no",
        "severity",
        "signal_atom",
        "source_key",
        "detail",
        "detail_json",
        "suggested_action",
        "status",
        "raw_payload_hash",
    ]
    + COMMON_COLUMNS,
}

EXTRA_COLUMN_DEFS = {
    TABLE_ATOM_LANE_MAPPING: {
        "link_id": "varchar(32) DEFAULT NULL COMMENT '可计算路网进口道路段标准编码'",
    },
    TABLE_PLAN_CFG: {
        "schema_version": "varchar(64) DEFAULT NULL COMMENT '标准化方案 schema 版本'",
        "signal_atom_json": "json DEFAULT NULL COMMENT '方案内信号原子快照'",
        "movement_mapping_json": "json DEFAULT NULL COMMENT 'atom 级 movement 映射摘要'",
        "parse_quality_json": "json DEFAULT NULL COMMENT '解析质量摘要'",
    },
    TABLE_QUALITY_ISSUE: {
        "stage_no": "int DEFAULT NULL COMMENT '阶段号'",
        "severity": "varchar(32) DEFAULT NULL COMMENT '问题严重级别'",
        "signal_atom": "varchar(64) DEFAULT NULL COMMENT '相关信号原子'",
        "source_key": "varchar(32) DEFAULT NULL COMMENT 'P/OP 来源'",
        "detail_json": "json DEFAULT NULL COMMENT '结构化问题详情'",
        "suggested_action": "varchar(255) DEFAULT NULL COMMENT '建议处理动作'",
        "status": "varchar(32) DEFAULT NULL COMMENT 'open/confirmed/ignored/fixed'",
    },
}

CREATE_ATOM_LANE_MAPPING_SQL = f"""
CREATE TABLE IF NOT EXISTS `{TABLE_ATOM_LANE_MAPPING}` (
  `inter_id` varchar(32) NOT NULL,
  `cross_id` varchar(32) DEFAULT NULL,
  `plan_no` int DEFAULT NULL,
  `stage_no` int DEFAULT NULL,
  `signal_atom` varchar(64) NOT NULL,
  `source_key` varchar(32) DEFAULT NULL,
  `source_type` varchar(32) DEFAULT NULL,
  `vendor_tag` varchar(32) DEFAULT NULL,
  `dir8_no` int DEFAULT NULL,
  `turn_dir_no` int DEFAULT NULL COMMENT '标准转向编码：1-左转（含调头），2-直行，3-右转',
  `link_id` varchar(32) DEFAULT NULL COMMENT '可计算路网进口道路段标准编码',
  `lane_group_id` varchar(64) DEFAULT NULL,
  `lane_nos_json` json DEFAULT NULL,
  `cluster_kind` varchar(64) DEFAULT NULL,
  `capabilities_json` json DEFAULT NULL,
  `movement_key` varchar(128) DEFAULT NULL,
  `confidence` varchar(32) DEFAULT NULL,
  `score` int DEFAULT NULL,
  `evidence_json` json DEFAULT NULL,
  `flow_green_check_json` json DEFAULT NULL,
  `schema_version` varchar(64) DEFAULT NULL,
  `create_time` datetime DEFAULT NULL,
  `update_time` datetime DEFAULT NULL,
  `is_deleted` tinyint DEFAULT 0,
  KEY `idx_atom_mapping_plan` (`inter_id`, `plan_no`, `signal_atom`, `source_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='信号原子与车道簇映射表'
"""

CREATE_STAGE_PHASE_RLTN_SQL = f"""
CREATE TABLE IF NOT EXISTS `{TABLE_PLAN_STAGE_PHASE_RLTN}` (
  `inter_id` varchar(32) NOT NULL COMMENT '标准路口ID',
  `cross_id` varchar(32) DEFAULT NULL COMMENT '信控机/海信路口ID',
  `plan_no` int NOT NULL COMMENT '方案号',
  `stage_seq_no` int NOT NULL COMMENT '方案内阶段序号',
  `stage_no` int NOT NULL COMMENT '标准阶段号',
  `source_type` varchar(16) NOT NULL COMMENT 'PHASE/OVERLAP',
  `source_no` int NOT NULL COMMENT '原始相位号或跟随相位槽位号，1基',
  `source_key` varchar(32) NOT NULL COMMENT 'P{{n}}/OP{{n}}',
  `ring_no` int DEFAULT NULL COMMENT '主相位所在环号，跟随相位为空',
  `barrier_seq_no` int DEFAULT NULL COMMENT '屏障分段序号，1基',
  `phase_seq_no` int DEFAULT NULL COMMENT '该相位在本环内的顺序，1基',
  `is_active_green` tinyint NOT NULL DEFAULT 1 COMMENT '是否在阶段绿灯切片内放行',
  `included_phase_nos_json` json DEFAULT NULL COMMENT '跟随相位母相位集合，仅 OVERLAP 使用',
  `modifier_phase_nos_json` json DEFAULT NULL COMMENT '跟随相位修正相位集合，仅 OVERLAP 使用',
  `evidence_json` json DEFAULT NULL COMMENT '阶段描述、时间片、原始解析证据',
  `remark` varchar(255) DEFAULT NULL,
  `create_time` datetime DEFAULT NULL,
  `update_time` datetime DEFAULT NULL,
  `is_deleted` tinyint DEFAULT 0,
  PRIMARY KEY (`inter_id`, `plan_no`, `stage_seq_no`, `source_type`, `source_no`),
  KEY `idx_stage_phase_stage` (`inter_id`, `plan_no`, `stage_no`),
  KEY `idx_stage_phase_source` (`inter_id`, `plan_no`, `source_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='标准阶段与海信原始环相位/跟随相位关系表'
"""

DIR_CODE = {
    "北": 0,
    "东北": 1,
    "东": 2,
    "东南": 3,
    "南": 4,
    "西南": 5,
    "西": 6,
    "西北": 7,
}

FLOW_TYPES = {
    "直": (1, "机动车直行"),
    "左": (2, "机动车左转"),
    "右": (3, "机动车右转"),
    "掉": (4, "机动车掉头"),
    "行人": (5, "行人"),
    "其他": (9, "其他"),
}

WEEKDAY_NO = {
    "周一": 1,
    "周二": 2,
    "周三": 3,
    "周四": 4,
    "周五": 5,
    "周六": 6,
    "周日": 7,
    "星期一": 1,
    "星期二": 2,
    "星期三": 3,
    "星期四": 4,
    "星期五": 5,
    "星期六": 6,
    "星期日": 7,
    "星期天": 7,
}

WEEKDAY_PATTERN = re.compile("|".join(sorted(WEEKDAY_NO, key=len, reverse=True)))
PLAN_NO_PATTERN = re.compile(r"方案\s*(\d+)")
STANDARD_INTER_ID_PATTERN = re.compile(r"^011[0-9A-Za-z]{13}$")


@dataclass(frozen=True)
class PlanKey:
    inter_id: str
    plan_no: int


@dataclass(frozen=True)
class StagePhaseRef:
    source_type: str
    source_no: int
    source_key: str
    ring_no: int | None = None
    barrier_seq_no: int | None = None
    phase_seq_no: int | None = None
    is_active_green: bool = False
    included_phase_nos: tuple[int, ...] = ()
    modifier_phase_nos: tuple[int, ...] = ()


@dataclass
class StageTiming:
    desc: list[str]
    green_sec: int = 0
    yellow_sec: int = 0
    all_red_sec: int = 0
    # 该阶段期间放行的信号机相位号（1 基），用于按相位聚合最小绿/最大绿
    phase_nos: set[int] = field(default_factory=set)
    phase_refs: dict[tuple[str, int], StagePhaseRef] = field(default_factory=dict)

    @property
    def total_sec(self) -> int:
        return self.green_sec + self.yellow_sec + self.all_red_sec


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_int(value: Any, default: int = 0) -> int:
    text = _clean(value)
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def _standard_turn_dir_no(value: Any) -> int | str:
    """统一 DWD 转向编码：1-左/掉，2-直，3-右。"""
    turn_dir_no = _to_int(value, default=-1)
    if turn_dir_no in {0, 1}:
        return 1
    if turn_dir_no in {2, 3}:
        return turn_dir_no
    return ""


def _pattern_to_plan_no(value: Any) -> int:
    """海信 pattern 与计划表方案号关系：pattern = 方案号 * 3 - 2。"""
    pattern = _to_int(value)
    if pattern <= 0:
        return 0
    return (pattern + 2) // 3


def _inter_id(hisense_id: Any) -> str:
    text = _clean(hisense_id)
    return text.zfill(16) if text.isdigit() else text[:16]


def _is_standard_inter_id(value: Any) -> bool:
    return bool(STANDARD_INTER_ID_PATTERN.fullmatch(_clean(value)))


def _cross_id(hisense_id: Any) -> str:
    text = _clean(hisense_id)
    return text.zfill(12) if text.isdigit() else text[:12]


def _source_inter_id(row: dict[str, Any], *fallback_keys: str) -> str:
    inter_id = _clean(row.get("inter_id"))
    if _is_standard_inter_id(inter_id):
        return inter_id[:16]
    for key in fallback_keys:
        value = _clean(row.get(key))
        if _is_standard_inter_id(value):
            return value[:16]
    return ""


def _source_cross_id(row: dict[str, Any], *fallback_keys: str) -> str:
    for key in fallback_keys:
        value = _clean(row.get(key))
        if value:
            return _cross_id(value)
    return ""


def _build_hisense_inter_id_map(rows: list[dict[str, str]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in rows:
        hisense_id = _clean(row.get("海信id"))
        inter_id = _clean(row.get("inter_id"))
        if hisense_id and _is_standard_inter_id(inter_id):
            mapping[hisense_id] = inter_id[:16]
    return mapping


def _json_dumps(value: Any) -> str:
    # default=str：兼容 MySQL 行中的 datetime 等非 JSON 原生类型（仅用于哈希/快照）
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _hash_payload(value: Any) -> str:
    raw = _json_dumps(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _common(batch_id: str, raw_payload_hash: str, ts: str) -> dict[str, Any]:
    _ = (batch_id, raw_payload_hash)
    return {
        "create_time": ts,
        "update_time": ts,
        "is_deleted": 0,
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _row_cell(row: dict[str, Any], aliases: tuple[str, ...]) -> str:
    """按别名顺序取行内首个存在的列值（新 ODS 列名优先，兼容旧列名）。"""
    for name in aliases:
        if name in row:
            return _clean(row.get(name))
    return ""


def _split_ints(text: Any, size: int = 16) -> list[int]:
    values: list[int] = []
    for part in _clean(text).split():
        values.append(_to_int(part))
    while len(values) < size:
        values.append(0)
    return values[:size]


def _normalize_time(value: Any, *, default: str = "") -> str:
    text = _clean(value)
    if not text:
        return default
    if ":" not in text:
        return default
    hour_text, minute_text = text.split(":", 1)
    return f"{_to_int(hour_text):02d}:{_to_int(minute_text):02d}"


def _time_to_minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def _parse_weekdays(text: str) -> list[int]:
    normalized = text.strip()
    if normalized in {"每天", "每日", "全周"}:
        return [1, 2, 3, 4, 5, 6, 7]
    if normalized in {"工作日", "平日"}:
        return [1, 2, 3, 4, 5]
    if normalized in {"周末", "双休日", "双休日周末"}:
        return [6, 7]
    matches = [(m.group(0), WEEKDAY_NO[m.group(0)]) for m in WEEKDAY_PATTERN.finditer(text)]
    if not matches:
        return []
    if "到" in text and len(matches) >= 2:
        start = matches[0][1]
        end = matches[-1][1]
        if start <= end:
            return list(range(start, end + 1))
        return list(range(start, 8)) + list(range(1, end + 1))
    out: list[int] = []
    for _, no in matches:
        if no not in out:
            out.append(no)
    return out


def _weekday_token_to_no(token: str) -> int | None:
    text = token.strip()
    if text in {"日", "天", "7", "周日", "周天", "星期日", "星期天"}:
        return 7
    if text.isdigit():
        value = int(text)
        return value if 1 <= value <= 7 else None
    return WEEKDAY_NO.get(text) or WEEKDAY_NO.get(f"周{text}") or WEEKDAY_NO.get(f"星期{text}")


def _format_weekdays_from_schedule_rule(rule: str) -> str:
    match = re.search(r"星期\s*:\s*([^ ]+)", rule)
    if not match:
        return _clean(rule)

    raw = match.group(1).strip()
    if not raw:
        return _clean(rule)

    if "-" in raw:
        start_text, end_text = raw.split("-", 1)
        start = _weekday_token_to_no(start_text)
        end = _weekday_token_to_no(end_text)
        if start is None or end is None:
            return _clean(rule)
        names = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
        return f"{names[start]}到{names[end]}"

    weekdays: list[int] = []
    for part in re.split(r"[,，、]", raw):
        value = _weekday_token_to_no(part)
        if value is not None and value not in weekdays:
            weekdays.append(value)
    if not weekdays:
        return _clean(rule)
    names = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
    return "".join(names[value] for value in weekdays)


def _plan_no_from_action(action: Any) -> int:
    text = _clean(action)
    match = PLAN_NO_PATTERN.search(text)
    return int(match.group(1)) if match else 0


def _is_new_schedule_format(rows: list[dict[str, str]]) -> bool:
    if not rows:
        return False
    keys = set(rows[0])
    return {"inter_id", "路口信控id", "原列1", "原列5", "原列6"}.issubset(keys)


def _normalize_new_schedule_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    current_applicable_time: dict[tuple[str, str], str] = {}

    for row in rows:
        inter_id = _source_inter_id(row, "路口信控id")
        if not inter_id:
            continue
        controller_id = _clean(row.get("路口信控id"))
        block_no = _clean(row.get("方案块序号"))
        block_key = (inter_id, block_no)
        rule = _clean(row.get("原列1"))
        start_time = _clean(row.get("原列5"))
        action = _clean(row.get("原列6"))

        if rule == "调度" or start_time == "时段" or action == "方案/周期":
            continue
        if rule:
            current_applicable_time[block_key] = _format_weekdays_from_schedule_rule(rule)
        applicable_time = current_applicable_time.get(block_key, "")
        if not start_time and not action:
            continue

        normalized.append(
            {
                "inter_id": inter_id,
                "cross_id": _source_cross_id(row, "路口信控id"),
                "海信路口名称": _clean(row.get("路口名")),
                "海信ID": controller_id,
                "适用时间": applicable_time,
                "开始时间": start_time,
                "结束时间": "",
                "方案号": str(_plan_no_from_action(action)),
                "备注": action,
                "方案块序号": block_no,
            }
        )

    return normalized


PERIOD_END_TIME_PATTERN = re.compile(r"时段[:：]\s*\d{1,2}:\d{2}\s*-\s*(\d{1,2}:\d{2})")


def _is_ods_schedule_format(rows: list[dict[str, str]]) -> bool:
    if not rows:
        return False
    keys = set(rows[0])
    return {"schedule_desc", "period_time", "original_scheme_desc"}.issubset(keys)


def _normalize_ods_schedule_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """ODS 调度时段表 ods_ctl_inter_schedule_period_raw 归一化为通用调度行结构。"""
    normalized: list[dict[str, str]] = []
    for row in rows:
        inter_id = _source_inter_id(row)
        if not inter_id:
            continue
        end_match = PERIOD_END_TIME_PATTERN.search(_clean(row.get("original_scheme_desc")))
        normalized.append(
            {
                "inter_id": inter_id,
                "cross_id": _source_cross_id(row, "cross_id"),
                "海信路口名称": _clean(row.get("inter_name")),
                "海信ID": _clean(row.get("cross_id")),
                "适用时间": _clean(row.get("schedule_desc")),
                "开始时间": _clean(row.get("period_time")),
                "结束时间": end_match.group(1) if end_match else "",
                "方案号": _clean(row.get("plan_no")),
                "备注": _clean(row.get("remark")) or _clean(row.get("original_scheme_desc")),
                "方案块序号": "",
            }
        )
    return normalized


def _normalize_schedule_rows(
    rows: list[dict[str, str]],
    hisense_inter_id_map: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    if _is_ods_schedule_format(rows):
        return _normalize_ods_schedule_rows(rows)
    if _is_new_schedule_format(rows):
        return _normalize_new_schedule_rows(rows)
    hisense_inter_id_map = hisense_inter_id_map or {}
    normalized: list[dict[str, str]] = []
    for row in rows:
        copied = dict(row)
        hisense_id = _clean(copied.get("海信ID"))
        inter_id = _source_inter_id(copied) or hisense_inter_id_map.get(hisense_id, "")
        if not inter_id:
            continue
        copied["inter_id"] = inter_id
        copied["cross_id"] = _source_cross_id(copied, "海信ID")
        copied.setdefault("方案块序号", "")
        normalized.append(copied)
    return normalized


def _parse_direction_atom(atom: str) -> tuple[str, str, list[tuple[int, str]]]:
    direction = ""
    suffix = atom
    for candidate in sorted(DIR_CODE, key=len, reverse=True):
        if atom.startswith(candidate):
            direction = candidate
            suffix = atom[len(candidate) :]
            break

    if "行人" in suffix or suffix in {"入行", "出行"}:
        return direction, suffix, [FLOW_TYPES["行人"]]

    flow_keys: list[str] = []
    for key in ("直", "左", "右", "掉"):
        if key in suffix:
            flow_keys.append(key)
    if not flow_keys:
        flow_keys.append("其他")

    flows = [FLOW_TYPES[key] for key in flow_keys]
    return direction, suffix, flows


def _stage_flow_combo(stage_desc: list[str]) -> list[dict[str, Any]]:
    combo: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for atom in stage_desc:
        direction, _, flows = _parse_direction_atom(atom)
        dir_no = DIR_CODE.get(direction, "")
        signal_atom = parse_signal_atom(atom).to_dict()
        for flow_type_no, flow_type_name in flows:
            key = (atom, dir_no, flow_type_no)
            if key in seen:
                continue
            seen.add(key)
            combo.append(
                {
                    "from_link_id": "",
                    "f_dir8_no": dir_no,
                    "f_dir8_name": direction,
                    "flow_type_no": flow_type_no,
                    "flow_type_name": flow_type_name,
                    "signal_atom": atom,
                    "vendor_tag": signal_atom["vendorTag"],
                    "source_key": "",
                    "source_type": "",
                    "turn_set": signal_atom["turnSet"],
                    "movement_key": movement_key_for_atom(atom, ""),
                }
            )
    return combo


def _stage_identity(stage_desc: list[str]) -> str:
    return _json_dumps(stage_desc)


def _merge_phase_refs(
    target: dict[tuple[str, int], StagePhaseRef],
    refs: dict[tuple[str, int], StagePhaseRef] | None,
) -> None:
    if not refs:
        return
    for key, ref in refs.items():
        existing = target.get(key)
        if existing is None or (ref.is_active_green and not existing.is_active_green):
            target[key] = ref


def _build_phase_position_index(rings: list[dict[str, list]]) -> dict[int, dict[str, int]]:
    positions: dict[int, dict[str, int]] = {}
    for ring_idx, ring in enumerate(rings, start=1):
        phases = [int(phase) for phase in ring.get("phases") or []]
        segments = phases_to_barrier_segments(phases, ring.get("barriers") or [])
        for barrier_idx, segment in enumerate(segments, start=1):
            for phase_no in segment:
                if phase_no in positions:
                    continue
                positions[phase_no] = {
                    "ring_no": ring_idx,
                    "barrier_seq_no": barrier_idx,
                    "phase_seq_no": phases.index(phase_no) + 1,
                }
    return positions


def _extract_plan_signal_atoms(
    row: dict[str, Any],
    channelization: dict[str, object] | None = None,
) -> list[dict[str, Any]]:
    phase_data = load_phase_data(_row_cell(row, PHASE_COLUMN_ALIASES))
    if not phase_data:
        return []
    cycle_cell = _row_cell(row, CYCLE_COLUMN_ALIASES)
    overlap_phases = load_overlap_phases(_row_cell(row, OVERLAP_COLUMN_ALIASES))
    parent_evidence_movements = build_phase_movements(phase_data, cycle_cell)
    phase_movements = build_phase_movements(phase_data, cycle_cell, overlap_phases)
    try:
        rings = parse_cycle_list_ordered(cycle_cell)
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        return []
    used_phases = {ph for ring in rings for ph in ring["phases"]} if rings else set()
    phase_movements, overlap_phases = _drop_contained_motor_flows(
        phase_movements,
        overlap_phases,
        used_phases,
        parent_evidence_movements=parent_evidence_movements,
    )

    atom_sources: dict[str, set[str]] = defaultdict(set)
    for ph in used_phases:
        if 1 <= ph <= 16:
            for is_ped, atom in phase_movements[ph - 1]:
                if not is_ped:
                    atom_sources[atom].add(f"P{ph}")
    for ov in overlap_phases:
        if ov.included & used_phases:
            for is_ped, atom in ov.atoms:
                if not is_ped:
                    atom_sources[atom].add(f"OP{ov.overlap_no}")

    atoms: list[dict[str, Any]] = []
    for atom, sources in sorted(atom_sources.items()):
        for source_key in sorted(sources):
            atoms.append(parse_signal_atom(atom, source_key=source_key).to_dict())
    for atom in sorted(
        infer_left_follow_atoms_from_channelization(
            [stage.desc for stage in _load_stage_timings(row)],
            channelization,
        )
    ):
        dir8_no = _dir8_no_from_atom(atom)
        source_key = f"IFL{dir8_no}" if dir8_no is not None else "IFL"
        atoms.append(parse_signal_atom(atom, source_key=source_key).to_dict())
    return atoms


def _dir8_no_from_atom(atom: str) -> int | None:
    direction = ""
    for ch in atom:
        if ch not in "东南西北":
            break
        direction += ch
    return {
        "北": 0,
        "东北": 1,
        "东": 2,
        "东南": 3,
        "南": 4,
        "西南": 5,
        "西": 6,
        "西北": 7,
    }.get(direction)


def _build_stage_rows(
    *,
    inter_id: str,
    cross_id: str,
    stage_desc: list[str],
    stage_no: int,
    batch_id: str,
    raw_payload_hash: str,
    ts: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    flow_combo = _stage_flow_combo(stage_desc)
    common = _common(batch_id, raw_payload_hash, ts)
    stage_name = "、".join(stage_desc) if stage_desc else f"空阶段{stage_no}"
    stage_remark = ""
    if not flow_combo:
        stage_remark = "源数据未解析出交通流组合"

    stage_row = {
        "inter_id": inter_id,
        "cross_id": cross_id,
        "signal_controller_id": cross_id,
        "stage_no": stage_no,
        "stage_name": stage_name,
        "flow_combo_json": _json_dumps(flow_combo),
        "remark": stage_remark,
        **common,
    }

    motor_rows: list[dict[str, Any]] = []
    flow_seq_no = 1
    for flow in flow_combo:
        if int(flow["flow_type_no"]) not in {1, 2, 3, 4, 9}:
            continue
        motor_rows.append(
            {
                "inter_id": inter_id,
                "cross_id": cross_id,
                "stage_no": stage_no,
                "flow_seq_no": flow_seq_no,
                "from_link_id": "",
                "f_dir8_no": flow["f_dir8_no"],
                "flow_type_no": flow["flow_type_no"],
                "flow_type_name": flow["flow_type_name"],
                "lane_id_list": "[]",
                "remark": "输入文件无路网 link 映射，from_link_id 暂为空",
                **common,
            }
        )
        flow_seq_no += 1
    return stage_row, motor_rows


def _phase_total(phase_no: int, green: list[int], yellow: list[int], red: list[int]) -> int:
    idx = phase_no - 1
    if idx < 0 or idx >= len(green):
        return 0
    return green[idx] + yellow[idx] + red[idx]


def _phase_color_at(phase_no: int, elapsed: int, green: list[int], yellow: list[int]) -> str:
    idx = phase_no - 1
    if idx < 0 or idx >= len(green):
        return "red"
    if elapsed < green[idx]:
        return "green"
    if elapsed < green[idx] + yellow[idx]:
        return "yellow"
    return "red"


def _next_phase_color_boundary(
    phase_no: int,
    elapsed: int,
    green: list[int],
    yellow: list[int],
    red: list[int],
) -> int:
    idx = phase_no - 1
    if idx < 0 or idx >= len(green):
        return 0
    total = green[idx] + yellow[idx] + red[idx]
    for boundary in (green[idx], green[idx] + yellow[idx], total):
        if boundary > elapsed:
            return boundary
    return total


def _interval_color(states: list[str]) -> str:
    if states and all(state == "red" for state in states):
        return "red"
    if any(state == "yellow" for state in states):
        return "yellow"
    return "green"


def _append_stage_interval(
    stages: list[StageTiming],
    desc: list[str],
    color: str,
    seconds: int,
    phase_nos: set[int] | None = None,
    phase_refs: dict[tuple[str, int], StagePhaseRef] | None = None,
) -> None:
    if seconds <= 0:
        return
    if stages and stages[-1].desc == desc:
        target = stages[-1]
    else:
        target = StageTiming(desc=list(desc))
        stages.append(target)
    if phase_nos:
        target.phase_nos.update(phase_nos)
    _merge_phase_refs(target.phase_refs, phase_refs)
    if color == "yellow":
        # 黄灯是相位级清空参数；多环/跨阶段切片只说明时间线被切开，
        # 不应把多个相位或多个切片的黄灯累加到同一车流参数上。
        target.yellow_sec = max(target.yellow_sec, seconds)
    elif color == "red":
        target.all_red_sec = max(target.all_red_sec, seconds)
    else:
        target.green_sec += seconds


def _apply_phase_clearance_timing(
    stages: list[StageTiming],
    yellow: list[int],
    red: list[int],
) -> None:
    """将阶段黄灯/全红归一为相位级清空参数，而非时间线切片累计值。"""
    for stage in stages:
        phase_indices = [phase_no - 1 for phase_no in stage.phase_nos if phase_no > 0]
        if stage.yellow_sec > 0:
            stage.yellow_sec = max(
                [yellow[idx] for idx in phase_indices if idx < len(yellow)] or [stage.yellow_sec]
            )
        if stage.all_red_sec > 0:
            stage.all_red_sec = max(
                [red[idx] for idx in phase_indices if idx < len(red)] or [stage.all_red_sec]
            )


def _simulate_segment_with_color_timing(
    segment_phases_per_ring: list[list[int]],
    green: list[int],
    yellow: list[int],
    red: list[int],
    phase_movements: list[list[tuple[bool, str]]],
    overlap_phases: list[OverlapPhase] | None = None,
    phase_position_by_no: dict[int, dict[str, int]] | None = None,
) -> list[StageTiming]:
    n = len(segment_phases_per_ring)
    ptr = [0] * n
    elapsed = [0] * n
    stages: list[StageTiming] = []

    def skip_finished_or_zero_duration(ring_idx: int) -> None:
        while ptr[ring_idx] < len(segment_phases_per_ring[ring_idx]):
            phase_no = segment_phases_per_ring[ring_idx][ptr[ring_idx]]
            total = _phase_total(phase_no, green, yellow, red)
            if total > elapsed[ring_idx]:
                break
            ptr[ring_idx] += 1
            elapsed[ring_idx] = 0

    for r_idx in range(n):
        skip_finished_or_zero_duration(r_idx)

    while any(ptr[r_idx] < len(segment_phases_per_ring[r_idx]) for r_idx in range(n)):
        active = [r_idx for r_idx in range(n) if ptr[r_idx] < len(segment_phases_per_ring[r_idx])]
        if not active:
            break

        phase_nos = [0] * n
        candidates: list[int] = []
        states: list[str] = []
        interval_phases: set[int] = set()
        for r_idx in active:
            phase_no = segment_phases_per_ring[r_idx][ptr[r_idx]]
            phase_nos[r_idx] = phase_no
            total = _phase_total(phase_no, green, yellow, red)
            boundary = _next_phase_color_boundary(phase_no, elapsed[r_idx], green, yellow, red)
            remaining = boundary - elapsed[r_idx]
            if total > elapsed[r_idx] and remaining > 0:
                candidates.append(remaining)
                states.append(_phase_color_at(phase_no, elapsed[r_idx], green, yellow))
                interval_phases.add(phase_no)

        if not candidates:
            for r_idx in active:
                skip_finished_or_zero_duration(r_idx)
            continue

        seconds = min(candidates)
        color = _interval_color(states)
        desc = _compose_stage_ordered_description(active, phase_nos, phase_movements, overlap_phases)
        concurrent_phases = {phase_nos[r_idx] for r_idx in active if phase_nos[r_idx] > 0}
        refs: dict[tuple[str, int], StagePhaseRef] = {}
        for phase_no in interval_phases:
            position = (phase_position_by_no or {}).get(phase_no, {})
            ref = StagePhaseRef(
                source_type="PHASE",
                source_no=phase_no,
                source_key=f"P{phase_no}",
                ring_no=position.get("ring_no"),
                barrier_seq_no=position.get("barrier_seq_no"),
                phase_seq_no=position.get("phase_seq_no"),
                is_active_green=color == "green",
            )
            refs[(ref.source_type, ref.source_no)] = ref
        for ov in overlap_phases or []:
            if not ov.is_active(concurrent_phases):
                continue
            ref = StagePhaseRef(
                source_type="OVERLAP",
                source_no=ov.overlap_no,
                source_key=f"OP{ov.overlap_no}",
                is_active_green=color == "green",
                included_phase_nos=tuple(sorted(ov.included)),
                modifier_phase_nos=tuple(sorted(ov.modifier)),
            )
            refs[(ref.source_type, ref.source_no)] = ref
        _append_stage_interval(stages, desc, color, int(seconds), interval_phases, refs)

        for r_idx in active:
            elapsed[r_idx] += seconds
            skip_finished_or_zero_duration(r_idx)

    _apply_phase_clearance_timing(stages, yellow, red)
    return stages


def _load_stage_timings(
    row: dict[str, str],
    channelization: dict[str, object] | None = None,
) -> list[StageTiming]:
    phase_data = load_phase_data(_row_cell(row, PHASE_COLUMN_ALIASES))
    if not phase_data:
        return []

    green = _split_ints(phase_data.get("greenTime"))
    yellow = _split_ints(phase_data.get("yellowTime"))
    red = _split_ints(phase_data.get("redTime"))
    cycle_cell = _row_cell(row, CYCLE_COLUMN_ALIASES)
    overlap_phases = load_overlap_phases(_row_cell(row, OVERLAP_COLUMN_ALIASES))
    parent_evidence_movements = build_phase_movements(phase_data, cycle_cell)
    phase_movements = build_phase_movements(phase_data, cycle_cell, overlap_phases)
    rings = parse_cycle_list_ordered(cycle_cell)
    if not rings:
        return []

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
    segment_count = min(len(segments) for segments in segments_per_ring) if segments_per_ring else 0
    phase_position_by_no = _build_phase_position_index(rings)

    all_stages: list[StageTiming] = []
    for segment_idx in range(segment_count):
        segment_rings = [
            segments_per_ring[ring_idx][segment_idx] for ring_idx in range(len(rings))
        ]
        for stage in _simulate_segment_with_color_timing(
            segment_rings,
            green,
            yellow,
            red,
            phase_movements,
            overlap_phases,
            phase_position_by_no,
        ):
            _append_stage_interval(
                all_stages, stage.desc, "green", stage.green_sec, stage.phase_nos, stage.phase_refs
            )
            _append_stage_interval(
                all_stages, stage.desc, "yellow", stage.yellow_sec, stage.phase_nos, stage.phase_refs
            )
            _append_stage_interval(
                all_stages, stage.desc, "red", stage.all_red_sec, stage.phase_nos, stage.phase_refs
            )
    _apply_phase_clearance_timing(all_stages, yellow, red)
    inferred_descs = apply_left_follow_inference([stage.desc for stage in all_stages], channelization)
    for stage, desc in zip(all_stages, inferred_descs, strict=False):
        stage.desc = desc
    return all_stages


def _plan_phase_bounds(row: dict[str, str]) -> tuple[list[int], list[int]]:
    """逐相位（1 基下标-1）的最小绿/最大绿数组，来自信号机 minGTime/maxGTime。"""
    phase_data = load_phase_data(_row_cell(row, PHASE_COLUMN_ALIASES))
    if not phase_data:
        return [0] * 16, [0] * 16
    return _split_ints(phase_data.get("minGTime")), _split_ints(phase_data.get("maxGTime"))


def _stage_phase_bound(bounds: list[int], phase_nos: set[int]) -> int | str:
    """阶段绿灯界 = 该阶段所辖各相位绿灯界的最大值；无有效数据返回空串。

    最小绿取 max：阶段需同时满足其并发放行各相位的最小绿；
    最大绿取 max：相位可能跨阶段延续，取宽松上界避免过度约束。
    """
    values = [
        bounds[phase_no - 1]
        for phase_no in phase_nos
        if 1 <= phase_no <= len(bounds) and bounds[phase_no - 1] > 0
    ]
    return max(values) if values else ""


def _stage_phase_relation_rows(
    *,
    inter_id: str,
    cross_id: str,
    plan_no: int,
    stage_seq_no: int,
    stage_no: int,
    stage_timing: StageTiming,
    common: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    refs = sorted(
        stage_timing.phase_refs.values(),
        key=lambda ref: (0 if ref.source_type == "PHASE" else 1, ref.source_no),
    )
    for ref in refs:
        evidence = {
            "stage_desc": stage_timing.desc,
            "phase_nos": sorted(stage_timing.phase_nos),
            "green_sec": stage_timing.green_sec,
            "yellow_sec": stage_timing.yellow_sec,
            "all_red_sec": stage_timing.all_red_sec,
        }
        rows.append(
            {
                "inter_id": inter_id,
                "cross_id": cross_id,
                "plan_no": plan_no,
                "stage_seq_no": stage_seq_no,
                "stage_no": stage_no,
                "source_type": ref.source_type,
                "source_no": ref.source_no,
                "source_key": ref.source_key,
                "ring_no": ref.ring_no or "",
                "barrier_seq_no": ref.barrier_seq_no or "",
                "phase_seq_no": ref.phase_seq_no or "",
                "is_active_green": 1 if ref.is_active_green else 0,
                "included_phase_nos_json": _json_dumps(list(ref.included_phase_nos)),
                "modifier_phase_nos_json": _json_dumps(list(ref.modifier_phase_nos)),
                "evidence_json": _json_dumps(evidence),
                "remark": "由 Ring-Barrier 仿真生成阶段与原始相位映射",
                **common,
            }
        )
    return rows


def _authoritative_cross_map(pairs: list[tuple[str, str]]) -> dict[str, str]:
    """同一 inter_id 映射到多个 cross_id 属于源数据错误；取最小 cross_id 作为权威映射，
    保证 scheme 表与 schedule 表两侧选择一致。"""
    cross_ids_by_inter: dict[str, set[str]] = defaultdict(set)
    for inter_id, cross_id in pairs:
        if inter_id and cross_id:
            cross_ids_by_inter[inter_id].add(cross_id)
    return {inter_id: min(ids) for inter_id, ids in cross_ids_by_inter.items()}


def build_plan_tables(
    timing_rows: list[dict[str, str]],
    *,
    batch_id: str,
    ts: str,
    channelization_by_inter: dict[str, dict[str, object]] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[PlanKey, dict[str, Any]], list[dict[str, Any]]]:
    tables = {
        TABLE_STAGE_CFG: [],
        TABLE_STAGE_MOTOR_FLOW: [],
        TABLE_PLAN_CFG: [],
        TABLE_PLAN_STAGE_TIMING: [],
        TABLE_PLAN_STAGE_PHASE_RLTN: [],
        TABLE_ATOM_LANE_MAPPING: [],
    }
    quality_issues: list[dict[str, Any]] = []
    plan_lookup: dict[PlanKey, dict[str, Any]] = {}
    stage_no_by_inter_and_identity: dict[str, dict[str, int]] = defaultdict(dict)
    stage_row_seen: set[tuple[str, int]] = set()

    authoritative_cross = _authoritative_cross_map(
        [
            (_source_inter_id(row, "海信id"), _source_cross_id(row, "cross_id", "海信id"))
            for row in timing_rows
        ]
    )

    for row in timing_rows:
        raw_hash = _hash_payload(row)
        inter_id = _source_inter_id(row, "海信id")
        if not inter_id:
            continue
        cross_id = _source_cross_id(row, "cross_id", "海信id")
        expected_cross = authoritative_cross.get(inter_id, cross_id)
        if cross_id and cross_id != expected_cross:
            quality_issues.append(
                {
                    "issue_type": "INTER_ID_CROSS_ID_CONFLICT",
                    "inter_id": inter_id,
                    "cross_id": cross_id,
                    "plan_no": _to_int(row.get("plan_no")),
                    "day_plan_no": "",
                    "detail": (
                        f"inter_id 同时映射多个 cross_id，权威取 {expected_cross}，"
                        f"跳过 cross_id={cross_id} 的方案行"
                    ),
                    "raw_payload_hash": raw_hash,
                    **_common(batch_id, raw_hash, ts),
                }
            )
            continue
        pattern = _to_int(_row_cell(row, PATTERN_COLUMN_ALIASES))
        # 新 ODS 表直接带 plan_no；旧 CSV 由 pattern 推导
        plan_no = _to_int(row.get("plan_no")) or _pattern_to_plan_no(pattern)
        cycle_len = _to_int(_row_cell(row, CYCLE_LEN_COLUMN_ALIASES))
        offset = _to_int(_row_cell(row, OFFSET_COLUMN_ALIASES))
        common = _common(batch_id, raw_hash, ts)
        channelization = (channelization_by_inter or {}).get(inter_id)

        try:
            stage_timings = _load_stage_timings(row, channelization=channelization)
        except Exception as exc:  # noqa: BLE001
            stage_timings = []
            quality_issues.append(
                {
                    "issue_type": "PLAN_STAGE_PARSE_FAILED",
                    "inter_id": inter_id,
                    "cross_id": cross_id,
                    "plan_no": plan_no,
                    "day_plan_no": "",
                    "detail": str(exc),
                    "raw_payload_hash": raw_hash,
                    **common,
                }
            )

        plan_key = PlanKey(inter_id, plan_no)
        signal_atoms = _extract_plan_signal_atoms(row, channelization=channelization)
        movement_mapping = mapping_summary(
            [
                {
                    "confidence": "low",
                    "signalAtom": atom["signalAtom"],
                    "movementKey": movement_key_for_atom(atom["signalAtom"], atom.get("sourceKey") or ""),
                }
                for atom in signal_atoms
            ]
        )
        for atom in signal_atoms:
            tables[TABLE_ATOM_LANE_MAPPING].append(
                {
                    "inter_id": inter_id,
                    "cross_id": cross_id,
                    "plan_no": plan_no,
                    "stage_no": "",
                    "signal_atom": atom["signalAtom"],
                    "source_key": atom.get("sourceKey") or "",
                    "source_type": atom.get("sourceType") or "",
                    "vendor_tag": atom.get("vendorTag") or "",
                    "dir8_no": atom.get("dir8No") or "",
                    "turn_dir_no": _standard_turn_dir_no(atom.get("turnDirNo")),
                    "link_id": "",
                    "lane_group_id": "",
                    "lane_nos_json": "[]",
                    "cluster_kind": "",
                    "capabilities_json": "[]",
                    "movement_key": movement_key_for_atom(
                        atom["signalAtom"], atom.get("sourceKey") or ""
                    ),
                    "confidence": "low",
                    "score": 0,
                    "evidence_json": _json_dumps(["no_lane_group_mapping_yet"]),
                    "flow_green_check_json": "{}",
                    "schema_version": "atom_lane_mapping_v1",
                    **common,
                }
            )
        plan_lookup[plan_key] = {
            "cycle_len_sec": cycle_len,
            "offset_sec": offset,
            "ctrl_mode": CTRL_MODE_COORD_TIMING if offset > 0 else CTRL_MODE_TIMING,
        }
        tables[TABLE_PLAN_CFG].append(
            {
                "inter_id": inter_id,
                "cross_id": cross_id,
                "signal_controller_id": cross_id,
                "plan_no": plan_no,
                "plan_name": f"{_row_cell(row, INTER_NAME_COLUMN_ALIASES)}方案{plan_no}",
                "cycle_len_sec": cycle_len,
                "coord_stage_no": 0,
                "offset_sec": offset,
                "stage_cnt": len(stage_timings),
                "plan_source_no": 1,
                "schema_version": "atom_lane_mapping_v1",
                "signal_atom_json": _json_dumps({"atoms": signal_atoms}),
                "movement_mapping_json": _json_dumps(movement_mapping),
                "parse_quality_json": _json_dumps({"issues": []}),
                "remark": f"海信路口ID={_clean(row.get('海信id')) or _clean(row.get('cross_id'))}; pattern={pattern}; ring_count={_clean(row.get('ring_count'))}",
                **common,
            }
        )

        min_green, max_green = _plan_phase_bounds(row)
        stage_sum = 0
        for seq_no, stage_timing in enumerate(stage_timings, start=1):
            stage_desc = stage_timing.desc
            identity = _stage_identity(stage_desc)
            inter_stage_map = stage_no_by_inter_and_identity[inter_id]
            if identity not in inter_stage_map:
                inter_stage_map[identity] = len(inter_stage_map) + 1
            stage_no = inter_stage_map[identity]

            if (inter_id, stage_no) not in stage_row_seen:
                stage_row, motor_rows = _build_stage_rows(
                    inter_id=inter_id,
                    cross_id=cross_id,
                    stage_desc=stage_desc,
                    stage_no=stage_no,
                    batch_id=batch_id,
                    raw_payload_hash=raw_hash,
                    ts=ts,
                )
                tables[TABLE_STAGE_CFG].append(stage_row)
                tables[TABLE_STAGE_MOTOR_FLOW].extend(motor_rows)
                stage_row_seen.add((inter_id, stage_no))

            stage_total = stage_timing.total_sec
            stage_sum += stage_total
            tables[TABLE_PLAN_STAGE_TIMING].append(
                {
                    "inter_id": inter_id,
                    "cross_id": cross_id,
                    "plan_no": plan_no,
                    "stage_seq_no": seq_no,
                    "stage_no": stage_no,
                    "green_sec": stage_timing.green_sec,
                    "yellow_sec": stage_timing.yellow_sec,
                    "all_red_sec": stage_timing.all_red_sec,
                    "max_green_sec": _stage_phase_bound(max_green, stage_timing.phase_nos),
                    "min_green_sec": _stage_phase_bound(min_green, stage_timing.phase_nos),
                    "stage_total_sec": stage_total,
                    "adjust_json": "[]",
                    "remark": "由 Ring-Barrier 仿真并按 greenTime/yellowTime/redTime 拆分生成",
                    **common,
                }
            )
            tables[TABLE_PLAN_STAGE_PHASE_RLTN].extend(
                _stage_phase_relation_rows(
                    inter_id=inter_id,
                    cross_id=cross_id,
                    plan_no=plan_no,
                    stage_seq_no=seq_no,
                    stage_no=stage_no,
                    stage_timing=stage_timing,
                    common=common,
                )
            )

        if cycle_len > 0 and stage_sum != cycle_len:
            quality_issues.append(
                {
                    "issue_type": "CYCLE_STAGE_SUM_MISMATCH",
                    "inter_id": inter_id,
                    "cross_id": cross_id,
                    "plan_no": plan_no,
                    "day_plan_no": "",
                    "detail": f"cycle_len={cycle_len}, stage_total_sum={stage_sum}",
                    "raw_payload_hash": raw_hash,
                    **common,
                }
            )

    return tables, plan_lookup, quality_issues


def build_day_plan_tables(
    schedule_rows: list[dict[str, str]],
    plan_lookup: dict[PlanKey, dict[str, Any]],
    *,
    hisense_inter_id_map: dict[str, str] | None = None,
    batch_id: str,
    ts: str,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    tables = {
        TABLE_DAY_PLAN_CFG: [],
        TABLE_DAY_PLAN_PERIOD: [],
        TABLE_SCHEDULE_CFG: [],
    }
    quality_issues: list[dict[str, Any]] = []
    schedule_rows = _normalize_schedule_rows(schedule_rows, hisense_inter_id_map)

    authoritative_cross = _authoritative_cross_map(
        [(_clean(row.get("inter_id")), _clean(row.get("cross_id"))) for row in schedule_rows]
    )
    kept_rows: list[dict[str, str]] = []
    for row in schedule_rows:
        inter_id = _clean(row.get("inter_id"))
        cross_id = _clean(row.get("cross_id"))
        expected_cross = authoritative_cross.get(inter_id, cross_id)
        if cross_id and cross_id != expected_cross:
            raw_hash = _hash_payload(row)
            quality_issues.append(
                {
                    "issue_type": "INTER_ID_CROSS_ID_CONFLICT",
                    "inter_id": inter_id,
                    "cross_id": cross_id,
                    "plan_no": _to_int(row.get("方案号")),
                    "day_plan_no": "",
                    "detail": (
                        f"inter_id 同时映射多个 cross_id，权威取 {expected_cross}，"
                        f"跳过 cross_id={cross_id} 的调度行"
                    ),
                    "raw_payload_hash": raw_hash,
                    **_common(batch_id, raw_hash, ts),
                }
            )
            continue
        kept_rows.append(row)
    schedule_rows = kept_rows

    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in schedule_rows:
        grouped[
            (
                _clean(row.get("inter_id")),
                _clean(row.get("方案块序号")),
                _clean(row.get("适用时间")),
            )
        ].append(row)

    day_plan_no_by_key: dict[tuple[str, str, str], int] = {}
    schedule_no_by_inter: dict[str, int] = defaultdict(int)
    for inter_id_key in sorted({k[0] for k in grouped}):
        keys = [k for k in grouped if k[0] == inter_id_key]
        for no, key in enumerate(sorted(keys, key=lambda x: (x[1], x[2])), start=1):
            day_plan_no_by_key[key] = no

    for key, rows in sorted(grouped.items(), key=lambda item: (item[0][0], day_plan_no_by_key[item[0]])):
        inter_id, _, applicable_time = key
        cross_id = _clean(rows[0].get("cross_id"))
        hisense_id = _clean(rows[0].get("海信ID"))
        day_plan_no = day_plan_no_by_key[key]
        first_row = rows[0]
        raw_hash = _hash_payload(rows)
        common = _common(batch_id, raw_hash, ts)

        normalized_rows = []
        for row in rows:
            start_time = _normalize_time(row.get("开始时间"), default="00:00")
            end_time = _normalize_time(row.get("结束时间"))
            normalized_rows.append((start_time, end_time, row))
        normalized_rows.sort(key=lambda item: _time_to_minutes(item[0]))

        tables[TABLE_DAY_PLAN_CFG].append(
            {
                "inter_id": inter_id,
                "cross_id": cross_id,
                "signal_controller_id": cross_id,
                "day_plan_no": day_plan_no,
                "day_plan_name": applicable_time,
                "period_cnt": len(normalized_rows),
                "remark": f"海信路口ID={hisense_id}; 路口名称={_clean(first_row.get('海信路口名称'))}",
                **common,
            }
        )

        for seq_no, (start_time, end_time, row) in enumerate(normalized_rows, start=1):
            if not end_time:
                if seq_no < len(normalized_rows):
                    end_time = normalized_rows[seq_no][0]
                else:
                    end_time = "24:00"
            plan_no = _to_int(row.get("方案号"))
            plan_meta = plan_lookup.get(PlanKey(inter_id, plan_no), {})
            if plan_no > 0 and not plan_meta:
                quality_issues.append(
                    {
                        "issue_type": "DAY_PLAN_REFERENCES_UNKNOWN_PLAN",
                        "inter_id": inter_id,
                        "cross_id": cross_id,
                        "plan_no": plan_no,
                        "day_plan_no": day_plan_no,
                        "detail": f"{applicable_time} {start_time}-{end_time} 引用配时方案表中不存在的方案",
                        "raw_payload_hash": raw_hash,
                        **common,
                    }
                )
            tables[TABLE_DAY_PLAN_PERIOD].append(
                {
                    "inter_id": inter_id,
                    "cross_id": cross_id,
                    "day_plan_no": day_plan_no,
                    "period_seq_no": seq_no,
                    "start_time": start_time,
                    "end_time": end_time,
                    "plan_no": plan_no,
                    "ctrl_mode": plan_meta.get("ctrl_mode", CTRL_MODE_TIMING),
                    "action_json": "[]",
                    "remark": _clean(row.get("备注")),
                    **common,
                }
            )

        weekdays = _parse_weekdays(applicable_time)
        if not weekdays:
            quality_issues.append(
                {
                    "issue_type": "SCHEDULE_WEEKDAY_PARSE_FAILED",
                    "inter_id": inter_id,
                    "cross_id": cross_id,
                    "plan_no": "",
                    "day_plan_no": day_plan_no,
                    "detail": f"无法解析适用时间: {applicable_time}",
                    "raw_payload_hash": raw_hash,
                    **common,
                }
            )
            weekdays = [0]
        for week_day_no in weekdays:
            schedule_no_by_inter[inter_id] += 1
            schedule_no = schedule_no_by_inter[inter_id]
            tables[TABLE_SCHEDULE_CFG].append(
                {
                    "inter_id": inter_id,
                    "cross_id": cross_id,
                    "signal_controller_id": cross_id,
                    "schedule_no": schedule_no,
                    "schedule_name": applicable_time,
                    "schedule_type_no": 3,
                    "priority_no": 100,
                    "start_day": "",
                    "end_day": "",
                    "week_day_no": "" if week_day_no == 0 else week_day_no,
                    "day_plan_no": day_plan_no,
                    "remark": "由计划表适用时间生成周调度",
                    **common,
                }
            )

    return tables, quality_issues


def build_standard_tables(
    timing_csv: Path,
    schedule_csv: Path,
    output_dir: Path,
    *,
    batch_id: str | None = None,
) -> dict[str, int]:
    ts = _now()
    batch_id = batch_id or f"ring_to_stage_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    timing_rows = _read_csv(timing_csv)
    schedule_rows = _read_csv(schedule_csv)

    hisense_inter_id_map = _build_hisense_inter_id_map(timing_rows)
    plan_tables, plan_lookup, plan_issues = build_plan_tables(timing_rows, batch_id=batch_id, ts=ts)
    day_plan_tables, day_plan_issues = build_day_plan_tables(
        schedule_rows,
        plan_lookup,
        hisense_inter_id_map=hisense_inter_id_map,
        batch_id=batch_id,
        ts=ts,
    )

    all_tables: dict[str, list[dict[str, Any]]] = {
        **plan_tables,
        **day_plan_tables,
        TABLE_QUALITY_ISSUE: plan_issues + day_plan_issues,
    }
    counts: dict[str, int] = {}
    for table_name, rows in all_tables.items():
        _write_csv(output_dir / f"{table_name}.csv", TABLE_COLUMNS[table_name], rows)
        counts[table_name] = len(rows)
    return counts


def _db_value(value: Any) -> Any:
    """CSV 风格的空串在严格模式下无法写入 int/time 等列，统一转为 NULL。"""
    if isinstance(value, str) and value == "":
        return None
    return value


def _fetch_source_rows(conn: Any, table_name: str) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(
            f"SELECT * FROM {_quote_identifier(table_name)} WHERE `is_deleted` = 0"
        )
        return list(cursor.fetchall())


def _replace_table_rows(
    conn: Any,
    table_name: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    batch_size: int = 500,
) -> None:
    """覆盖写入：先清空标准表，再批量插入本次解析结果。"""
    table_ident = _quote_identifier(table_name)
    with conn.cursor() as cursor:
        cursor.execute(f"TRUNCATE TABLE {table_ident}")
    quoted_columns = ", ".join(_quote_identifier(col) for col in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {table_ident} ({quoted_columns}) VALUES ({placeholders})"
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        values = [tuple(_db_value(row.get(col)) for col in columns) for row in batch]
        with conn.cursor() as cursor:
            cursor.executemany(sql, values)
    conn.commit()


def _ensure_schema_extensions(conn: Any) -> None:
    """Create/extend optional atom-level schema without changing existing column semantics."""
    with conn.cursor() as cursor:
        cursor.execute(CREATE_ATOM_LANE_MAPPING_SQL)
        cursor.execute(CREATE_STAGE_PHASE_RLTN_SQL)
    for table_name, column_defs in EXTRA_COLUMN_DEFS.items():
        table_ident = _quote_identifier(table_name)
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW COLUMNS FROM {table_ident}")
            existing = {row["Field"] if isinstance(row, dict) else row[0] for row in cursor.fetchall()}
        for column, definition in column_defs.items():
            if column in existing:
                continue
            with conn.cursor() as cursor:
                cursor.execute(
                    f"ALTER TABLE {table_ident} ADD COLUMN {_quote_identifier(column)} {definition}"
                )
    conn.commit()


def _fetch_channelization_by_inter(
    conn: Any,
    inter_ids: set[str],
) -> dict[str, dict[str, object]]:
    """Best-effort channelization lookup used for inferred left-follow movements."""
    if not inter_ids:
        return {}

    out: dict[str, dict[str, object]] = {}
    try:
        from data.mysql_reader import fetch_lane_channelization
    except Exception:
        fetch_lane_channelization = None

    for inter_id in sorted(inter_ids):
        if fetch_lane_channelization is None:
            continue
        try:
            channelization = fetch_lane_channelization(conn, inter_id)
        except Exception:
            continue
        if isinstance(channelization, dict) and channelization.get("approaches"):
            out[inter_id] = channelization

    missing = inter_ids - set(out)
    if not missing:
        return out

    try:
        from data.pg_reader import connect_pg, fetch_channelization
    except Exception:
        return out

    pg_conn = connect_pg()
    try:
        for inter_id in sorted(missing):
            try:
                channelization = fetch_channelization(pg_conn, inter_id)
            except Exception:
                continue
            if isinstance(channelization, dict) and channelization.get("approaches"):
                out[inter_id] = channelization
    finally:
        pg_conn.close()
    return out


def build_standard_tables_from_db(
    *,
    scheme_table: str = DEFAULT_SCHEME_TABLE,
    schedule_table: str = DEFAULT_SCHEDULE_TABLE,
    batch_id: str | None = None,
) -> dict[str, int]:
    """从 MySQL ODS 原始表解析并覆盖写回各信控标准表。"""
    ts = _now()
    batch_id = batch_id or f"ring_to_stage_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    conn = _get_mysql_connection()
    try:
        _ensure_schema_extensions(conn)
        timing_rows = _fetch_source_rows(conn, scheme_table)
        schedule_rows = _fetch_source_rows(conn, schedule_table)

        hisense_inter_id_map = _build_hisense_inter_id_map(timing_rows)
        inter_ids = {
            _source_inter_id(row, "海信id")
            for row in timing_rows
            if _source_inter_id(row, "海信id")
        }
        channelization_by_inter = _fetch_channelization_by_inter(conn, inter_ids)
        plan_tables, plan_lookup, plan_issues = build_plan_tables(
            timing_rows,
            batch_id=batch_id,
            ts=ts,
            channelization_by_inter=channelization_by_inter,
        )
        day_plan_tables, day_plan_issues = build_day_plan_tables(
            schedule_rows,
            plan_lookup,
            hisense_inter_id_map=hisense_inter_id_map,
            batch_id=batch_id,
            ts=ts,
        )

        all_tables: dict[str, list[dict[str, Any]]] = {
            **plan_tables,
            **day_plan_tables,
            TABLE_QUALITY_ISSUE: plan_issues + day_plan_issues,
        }
        counts: dict[str, int] = {}
        for table_name, rows in all_tables.items():
            _replace_table_rows(conn, table_name, TABLE_COLUMNS[table_name], rows)
            counts[table_name] = len(rows)
        return counts
    finally:
        conn.close()


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="海信配时 CSV 拆解为信控标准表 CSV")
    parser.add_argument(
        "--timing-csv",
        type=Path,
        default=base_dir / "配时方案.csv",
        help="配时方案 CSV 路径",
    )
    parser.add_argument(
        "--schedule-csv",
        type=Path,
        default=base_dir / "路口配时方案计划表.csv",
        help="路口配时方案计划表 CSV 路径",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=base_dir / "standard_tables",
        help="标准表 CSV 输出目录",
    )
    parser.add_argument("--batch-id", help="source_batch_id；默认按运行时间生成")
    parser.add_argument(
        "--from-db",
        action="store_true",
        help="从 MySQL ODS 原始表读取并覆盖写回标准表（替代 CSV 模式）",
    )
    parser.add_argument(
        "--scheme-table",
        default=DEFAULT_SCHEME_TABLE,
        help="配时方案 ODS 原始表名（--from-db 模式）",
    )
    parser.add_argument(
        "--schedule-table",
        default=DEFAULT_SCHEDULE_TABLE,
        help="调度时段 ODS 原始表名（--from-db 模式）",
    )
    args = parser.parse_args()

    if args.from_db:
        from env import load_project_env

        load_project_env()
        counts = build_standard_tables_from_db(
            scheme_table=args.scheme_table,
            schedule_table=args.schedule_table,
            batch_id=args.batch_id,
        )
        print("已覆盖写入 MySQL 标准表:")
    else:
        counts = build_standard_tables(
            args.timing_csv,
            args.schedule_csv,
            args.output_dir,
            batch_id=args.batch_id,
        )
        print(f"已写入标准表目录: {args.output_dir}")
    for table_name, count in counts.items():
        print(f"- {table_name}: {count}")


if __name__ == "__main__":
    main()
