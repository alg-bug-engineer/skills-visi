#!/usr/bin/env python3
"""生成路口历史配时参数聚合表 dws_ctl_inter_turn_5min_his_mm。

当前口径以 dwd_ctl_inter_period_plan_exec_his 为主数据源：
- 按 period_start_time/period_end_time 展开时段内重复执行的周期；
- 按阶段实际起止时间拆分到 5 分钟桶；
- 将阶段内放行的车流映射为 link_id + 标准 turn_dir_no(1/2/3)；
- 先聚合自然日 5 分钟桶，再按星期几与 step_index 做历史均值。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from preprocessing.timing.dir8_encoding import normalize_dir8_no
from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_PERIOD_PLAN_EXEC_HIS = "dwd_ctl_inter_period_plan_exec_his"
TABLE_ATOM_LANE_MAPPING = "dwd_ctl_inter_signal_atom_lane_mapping"
TABLE_SCHEDULE_CFG = "dwd_ctl_inter_schedule_cfg"
TABLE_DAY_PLAN_PERIOD = "dwd_ctl_inter_day_plan_period"
TABLE_PLAN_CFG = "dwd_ctl_inter_plan_cfg"
TABLE_PLAN_STAGE_TIMING = "dwd_ctl_inter_plan_stage_timing"
TABLE_STAGE_MOTOR_FLOW = "dwd_ctl_inter_stage_motor_flow_rltn"
TABLE_TARGET = "dws_ctl_inter_turn_5min_his_mm"

TARGET_COLUMNS = [
    "inter_id",
    "inter_name",
    "link_id",
    "turn_dir_no",
    "day_of_week",
    "step_index",
    "cycle_len_sec",
    "green_exec_sec",
    "yellow_exec_sec",
    "all_red_exec_sec",
    "plan_no",
    "ctrl_mode",
    "data_source_no",
    "is_deleted",
]

INTER_NAME_PATTERN = re.compile(r"路口名称=([^;]+)")
PLAN_NAME_PATTERN = re.compile(r"(.+?)方案\d+$")
BASE_WEEK_START = datetime(2000, 1, 3)  # Monday


@dataclass
class FlowMapping:
    link_id: str
    turn_dir_no: int | None


@dataclass
class PlanBucketStats:
    plan_no: int | None
    ctrl_mode: str | None = None
    data_source_no: int | None = None
    green_exec_sec: float = 0.0
    yellow_exec_sec: float = 0.0
    all_red_exec_sec: float = 0.0
    cycle_weighted_sum: float = 0.0
    cycle_weight_sec: float = 0.0
    param_sample_count: int = 0
    latest_period_start: datetime | None = None

    def mark_latest(
        self,
        *,
        ctrl_mode: str | None,
        data_source_no: int | None,
        period_start: datetime,
    ) -> None:
        if self.latest_period_start is None or period_start >= self.latest_period_start:
            self.latest_period_start = period_start
            self.ctrl_mode = ctrl_mode
            self.data_source_no = data_source_no


@dataclass
class BucketValue:
    inter_id: str
    inter_name: str
    link_id: str
    turn_dir_no: int
    bucket_date: date
    day_of_week: int
    step_index: int
    green_exec_sec: float = 0.0
    yellow_exec_sec: float = 0.0
    all_red_exec_sec: float = 0.0
    cycle_weighted_sum: float = 0.0
    cycle_weight_sec: float = 0.0
    param_sample_count: int = 0
    plan_no: int | None = None
    ctrl_mode: str | None = None
    data_source_no: int | None = None
    latest_period_start: datetime | None = None
    plan_stats: dict[int | None, PlanBucketStats] = field(default_factory=dict)

    def _stats_for_plan(
        self,
        *,
        plan_no: int | None,
        ctrl_mode: str | None,
        data_source_no: int | None,
        period_start: datetime,
    ) -> PlanBucketStats:
        stats = self.plan_stats.get(plan_no)
        if stats is None:
            stats = PlanBucketStats(plan_no=plan_no)
            self.plan_stats[plan_no] = stats
        stats.mark_latest(
            ctrl_mode=ctrl_mode,
            data_source_no=data_source_no,
            period_start=period_start,
        )
        return stats

    def selected_plan_stats(self) -> PlanBucketStats | None:
        if not self.plan_stats:
            return None
        return max(
            self.plan_stats.values(),
            key=lambda stats: (
                stats.latest_period_start or datetime.min,
                stats.param_sample_count,
                stats.cycle_weight_sec,
                stats.plan_no or 0,
            ),
        )

    def add_seconds(
        self,
        *,
        color: str,
        seconds: float,
        cycle_len_sec: int,
        plan_no: int | None,
        ctrl_mode: str | None,
        data_source_no: int | None,
        period_start: datetime,
    ) -> None:
        if color == "green":
            self.green_exec_sec += seconds
        elif color == "yellow":
            self.yellow_exec_sec += seconds
        elif color == "all_red":
            self.all_red_exec_sec += seconds
        self.cycle_weighted_sum += cycle_len_sec * seconds
        self.cycle_weight_sec += seconds
        stats = self._stats_for_plan(
            plan_no=plan_no,
            ctrl_mode=ctrl_mode,
            data_source_no=data_source_no,
            period_start=period_start,
        )
        if color == "green":
            stats.green_exec_sec += seconds
        elif color == "yellow":
            stats.yellow_exec_sec += seconds
        elif color == "all_red":
            stats.all_red_exec_sec += seconds
        stats.cycle_weighted_sum += cycle_len_sec * seconds
        stats.cycle_weight_sec += seconds
        if self.latest_period_start is None or period_start >= self.latest_period_start:
            self.latest_period_start = period_start
            self.plan_no = plan_no
            self.ctrl_mode = ctrl_mode
            self.data_source_no = data_source_no

    def add_param_sample(
        self,
        *,
        green_exec_sec: float,
        yellow_exec_sec: float,
        all_red_exec_sec: float,
        cycle_len_sec: int,
        plan_no: int | None,
        ctrl_mode: str | None,
        data_source_no: int | None,
        period_start: datetime,
    ) -> None:
        self.green_exec_sec += green_exec_sec
        self.yellow_exec_sec += yellow_exec_sec
        self.all_red_exec_sec += all_red_exec_sec
        self.cycle_weighted_sum += cycle_len_sec
        self.cycle_weight_sec += 1
        self.param_sample_count += 1
        stats = self._stats_for_plan(
            plan_no=plan_no,
            ctrl_mode=ctrl_mode,
            data_source_no=data_source_no,
            period_start=period_start,
        )
        stats.green_exec_sec += green_exec_sec
        stats.yellow_exec_sec += yellow_exec_sec
        stats.all_red_exec_sec += all_red_exec_sec
        stats.cycle_weighted_sum += cycle_len_sec
        stats.cycle_weight_sec += 1
        stats.param_sample_count += 1
        if self.latest_period_start is None or period_start >= self.latest_period_start:
            self.latest_period_start = period_start
            self.plan_no = plan_no
            self.ctrl_mode = ctrl_mode
            self.data_source_no = data_source_no


@dataclass
class HistoricAgg:
    inter_id: str
    inter_name: str
    link_id: str
    turn_dir_no: int
    day_of_week: int
    step_index: int
    sample_count: int = 0
    cycle_len_sec: float = 0.0
    green_exec_sec: float = 0.0
    yellow_exec_sec: float = 0.0
    all_red_exec_sec: float = 0.0
    plan_no: int | None = None
    ctrl_mode: str | None = None
    data_source_no: int | None = None
    latest_period_start: datetime | None = None

    def add_bucket(self, bucket: BucketValue) -> bool:
        stats = bucket.selected_plan_stats()
        if stats is None:
            return False
        self.sample_count += 1
        if stats.param_sample_count > 0:
            divisor = stats.param_sample_count
            self.cycle_len_sec += stats.cycle_weighted_sum / divisor
            self.green_exec_sec += stats.green_exec_sec / divisor
            self.yellow_exec_sec += stats.yellow_exec_sec / divisor
            self.all_red_exec_sec += stats.all_red_exec_sec / divisor
        else:
            cycle_len_sec = (
                stats.cycle_weighted_sum / stats.cycle_weight_sec
                if stats.cycle_weight_sec > 0
                else 0
            )
            self.cycle_len_sec += cycle_len_sec
            self.green_exec_sec += stats.green_exec_sec
            self.yellow_exec_sec += stats.yellow_exec_sec
            self.all_red_exec_sec += stats.all_red_exec_sec
        if self.latest_period_start is None or (
            stats.latest_period_start is not None
            and stats.latest_period_start >= self.latest_period_start
        ):
            self.latest_period_start = stats.latest_period_start
            self.plan_no = stats.plan_no
            self.ctrl_mode = stats.ctrl_mode
            self.data_source_no = stats.data_source_no
        return True

    def to_row(self) -> dict[str, Any]:
        divisor = max(self.sample_count, 1)
        return {
            "inter_id": self.inter_id,
            "inter_name": self.inter_name or None,
            "link_id": self.link_id,
            "turn_dir_no": self.turn_dir_no,
            "day_of_week": self.day_of_week,
            "step_index": self.step_index,
            "cycle_len_sec": round(self.cycle_len_sec / divisor),
            "green_exec_sec": round(self.green_exec_sec / divisor),
            "yellow_exec_sec": round(self.yellow_exec_sec / divisor),
            "all_red_exec_sec": round(self.all_red_exec_sec / divisor),
            "plan_no": self.plan_no,
            "ctrl_mode": self.ctrl_mode,
            "data_source_no": self.data_source_no,
            "is_deleted": 0,
        }


def _parse_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    text = str(value).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _time_to_seconds(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    if isinstance(value, time):
        return value.hour * 3600 + value.minute * 60 + value.second
    text = str(value).strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) < 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(float(parts[2])) if len(parts) > 2 else 0
    except ValueError:
        return None
    return hour * 3600 + minute * 60 + second


def _to_int(value: Any, default: int | None = 0) -> int | None:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def _standard_turn_from_flow_type(value: Any) -> int | None:
    flow_type_no = _to_int(value, default=None)
    if flow_type_no in {2, 4}:
        return 1
    if flow_type_no == 1:
        return 2
    if flow_type_no == 3:
        return 3
    return None


def _standard_turn_dir_no(value: Any) -> int | None:
    turn_dir_no = _to_int(value, default=None)
    if turn_dir_no in {0, 1}:
        return 1
    if turn_dir_no in {2, 3}:
        return turn_dir_no
    return None


def _day_of_week(value: datetime) -> int:
    return value.weekday() + 1


def _step_index(value: datetime) -> int:
    return min(287, (value.hour * 3600 + value.minute * 60 + value.second) // 300)


def _bucket_start(value: datetime) -> datetime:
    seconds = _step_index(value) * 300
    return datetime.combine(value.date(), time.min) + timedelta(seconds=seconds)


def _extract_inter_name(remark: Any) -> str:
    match = INTER_NAME_PATTERN.search(str(remark or ""))
    return match.group(1).strip() if match else ""


def _extract_inter_name_from_plan_name(plan_name: Any) -> str:
    text = str(plan_name or "").strip()
    match = PLAN_NAME_PATTERN.fullmatch(text)
    return match.group(1).strip() if match else ""


def _ensure_target_table(conn: Any, table_name: str) -> None:
    table_ident = _quote_identifier(table_name)
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
CREATE TABLE IF NOT EXISTS {table_ident} (
  `inter_id` varchar(16) NOT NULL COMMENT '可计算路网路口16位标准编码',
  `inter_name` varchar(128) DEFAULT NULL COMMENT '路口名称，便于直观识别',
  `link_id` varchar(32) NOT NULL COMMENT '可计算路网进口道路段16位标准编码',
  `turn_dir_no` tinyint NOT NULL COMMENT '转向类型：1-左转（含调头），2-直行，3-右转',
  `day_of_week` tinyint NOT NULL COMMENT '星期几：1-周一，2-周二，3-周三，4-周四，5-周五，6-周六，7-周日',
  `step_index` smallint NOT NULL COMMENT '5分钟时间片序号，取值0~287',
  `cycle_len_sec` int NOT NULL DEFAULT 0 COMMENT '历史平均周期时长（秒）',
  `green_exec_sec` int NOT NULL DEFAULT 0 COMMENT '历史平均绿灯时长（秒）',
  `yellow_exec_sec` int NOT NULL DEFAULT 0 COMMENT '历史平均黄灯时长（秒）',
  `all_red_exec_sec` int NOT NULL DEFAULT 0 COMMENT '历史平均全红时长（秒）',
  `plan_no` int DEFAULT NULL COMMENT '该时段执行的配时方案号',
  `ctrl_mode` varchar(2) DEFAULT NULL COMMENT '周期实际控制方式',
  `data_source_no` tinyint DEFAULT NULL COMMENT '数据来源：1-信控运行信息，2-信号机日志解析，3-灯态反推，9-其他',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
  `is_deleted` tinyint NOT NULL DEFAULT 0 COMMENT '逻辑删除标记：0-有效，1-已删除',
  PRIMARY KEY (`inter_id`, `link_id`, `turn_dir_no`, `day_of_week`, `step_index`),
  KEY `idx_inter_id_day_step` (`inter_id`, `day_of_week`, `step_index`),
  KEY `idx_day_of_week` (`day_of_week`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='路口历史配时参数聚合表 - 按路口+进口道路段+转向+星期几+5分钟时间片聚合'
""".strip()
        )
    conn.commit()


def ensure_atom_lane_mapping_extensions(
    conn: Any,
    table_name: str = TABLE_ATOM_LANE_MAPPING,
    *,
    normalize_turn_dir: bool = True,
) -> None:
    table_ident = _quote_identifier(table_name)
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM {table_ident}")
        existing = {row["Field"] if isinstance(row, dict) else row[0] for row in cursor.fetchall()}
        if "link_id" not in existing:
            cursor.execute(
                f"ALTER TABLE {table_ident} "
                "ADD COLUMN `link_id` varchar(32) DEFAULT NULL "
                "COMMENT '可计算路网进口道路段标准编码' AFTER `turn_dir_no`"
            )
        if normalize_turn_dir:
            cursor.execute(
                f"""
UPDATE {table_ident}
SET `turn_dir_no` = CASE
  WHEN `turn_dir_no` IN (0, 1) THEN 1
  WHEN `turn_dir_no` = 2 THEN 2
  WHEN `turn_dir_no` = 3 THEN 3
  ELSE `turn_dir_no`
END
WHERE `turn_dir_no` IS NOT NULL
""".strip()
            )
    conn.commit()


def fill_atom_mapping_link_id_from_pg(
    conn: Any,
    table_name: str = TABLE_ATOM_LANE_MAPPING,
) -> dict[str, int]:
    """从 PG 渠化宽表按 inter_id + dir8_no 统一进口 link_id（主路优先）。

    同一进口方向有多条 entrance link 时，取 lane_num 最大的主路 link，
    并将该方向下 atom 映射表的全部行强制更新为该 link_id（不仅限于空值行）。
    """
    from data.pg_reader import connect_pg, fetch_channelization

    table_ident = _quote_identifier(table_name)
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
SELECT DISTINCT inter_id
FROM {table_ident}
WHERE COALESCE(is_deleted, 0) = 0
  AND inter_id IS NOT NULL
  AND inter_id <> ''
""".strip()
        )
        inter_ids = [str(row.get("inter_id") or "") for row in cursor.fetchall()]

    counts = {
        "pg_fill_intersections": len(inter_ids),
        "pg_fill_updated_rows": 0,
        "pg_fill_unified_dirs": 0,
        "pg_fill_ambiguous_dirs": 0,
        "pg_fill_missing_dirs": 0,
    }
    if not inter_ids:
        return counts

    pg_conn = connect_pg()
    try:
        updates: list[tuple[str, str, int]] = []
        for inter_id in inter_ids:
            channelization = fetch_channelization(pg_conn, inter_id)
            links_by_dir8_no: dict[int, list[tuple[str, int]]] = defaultdict(list)
            for approach in channelization.get("approaches") or []:
                if str(approach.get("linkRole") or "") != "entrance":
                    continue
                link_id = str(approach.get("linkId") or "")
                dir8_no = normalize_dir8_no(approach.get("dir8Code"))
                if not link_id or dir8_no is None:
                    continue
                lane_num = _to_int(approach.get("laneTotal"), default=0) or 0
                links_by_dir8_no[dir8_no].append((link_id, lane_num))

            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
SELECT DISTINCT dir8_no
FROM {table_ident}
WHERE COALESCE(is_deleted, 0) = 0
  AND inter_id = %s
  AND dir8_no IS NOT NULL
""".strip(),
                    (inter_id,),
                )
                dir8_nos = [_to_int(row.get("dir8_no"), default=None) for row in cursor.fetchall()]

            for dir8_no in dir8_nos:
                if dir8_no is None:
                    continue
                candidates = links_by_dir8_no.get(dir8_no) or []
                if not candidates:
                    counts["pg_fill_missing_dirs"] += 1
                    continue
                unique_links = {link_id for link_id, _ in candidates}
                main_link_id, _ = max(candidates, key=lambda item: (item[1], item[0]))
                updates.append((main_link_id, inter_id, dir8_no))
                if len(unique_links) > 1:
                    counts["pg_fill_ambiguous_dirs"] += 1
                    counts["pg_fill_unified_dirs"] += 1

        if updates:
            with conn.cursor() as cursor:
                cursor.executemany(
                    f"""
UPDATE {table_ident}
SET link_id = %s
WHERE inter_id = %s
  AND dir8_no = %s
  AND COALESCE(is_deleted, 0) = 0
""".strip(),
                    updates,
                )
                counts["pg_fill_updated_rows"] = cursor.rowcount
        conn.commit()
    finally:
        pg_conn.close()
    return counts


def _load_flow_mappings(conn: Any, table_name: str) -> dict[tuple[str, int, str, str], FlowMapping]:
    table_ident = _quote_identifier(table_name)
    mappings: dict[tuple[str, int, str, str], FlowMapping] = {}
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
SELECT inter_id, plan_no, signal_atom, source_key, link_id, turn_dir_no
FROM {table_ident}
WHERE COALESCE(is_deleted, 0) = 0
""".strip()
        )
        for row in cursor.fetchall():
            signal_atom = str(row.get("signal_atom") or "")
            if not signal_atom:
                continue
            key = (
                str(row.get("inter_id") or ""),
                _to_int(row.get("plan_no"), default=0) or 0,
                signal_atom,
                str(row.get("source_key") or ""),
            )
            mappings[key] = FlowMapping(
                link_id=str(row.get("link_id") or ""),
                turn_dir_no=_standard_turn_dir_no(row.get("turn_dir_no")),
            )
    return mappings


def _load_unique_link_by_inter_dir(conn: Any, table_name: str) -> dict[tuple[str, int], str]:
    """读取 inter_id + 0 基 dir8_no 唯一 link_id 映射。"""
    table_ident = _quote_identifier(table_name)
    links: dict[tuple[str, int], str] = {}
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
SELECT inter_id, dir8_no, MIN(link_id) AS link_id, COUNT(DISTINCT link_id) AS link_cnt
FROM {table_ident}
WHERE COALESCE(is_deleted, 0) = 0
  AND link_id IS NOT NULL
  AND link_id <> ''
  AND dir8_no IS NOT NULL
GROUP BY inter_id, dir8_no
HAVING COUNT(DISTINCT link_id) = 1
""".strip()
        )
        for row in cursor.fetchall():
            dir8_no = normalize_dir8_no(row.get("dir8_no"), allow_legacy_one_based=True)
            link_id = str(row.get("link_id") or "")
            inter_id = str(row.get("inter_id") or "")
            if inter_id and dir8_no is not None and link_id:
                links[(inter_id, dir8_no)] = link_id
    return links


def _resolve_flow_mapping(
    *,
    mappings: dict[tuple[str, int, str, str], FlowMapping],
    inter_id: str,
    plan_no: int | None,
    flow: dict[str, Any],
    allow_dir8_fallback_link: bool,
) -> FlowMapping:
    signal_atom = str(flow.get("signal_atom") or "")
    source_key = str(flow.get("source_key") or "")
    plan_key = plan_no or 0
    mapping = (
        mappings.get((inter_id, plan_key, signal_atom, source_key))
        or mappings.get((inter_id, plan_key, signal_atom, ""))
        or mappings.get((inter_id, 0, signal_atom, source_key))
        or mappings.get((inter_id, 0, signal_atom, ""))
        or FlowMapping(link_id="", turn_dir_no=None)
    )
    link_id = mapping.link_id or str(flow.get("from_link_id") or "")
    if not link_id and allow_dir8_fallback_link:
        dir8_no = str(flow.get("f_dir8_no") or "").strip()
        link_id = f"dir8:{dir8_no}" if dir8_no else ""
    return FlowMapping(
        link_id=link_id,
        turn_dir_no=mapping.turn_dir_no or _standard_turn_from_flow_type(flow.get("flow_type_no")),
    )


def _resolve_schedule_flow_mapping(
    *,
    link_by_inter_dir: dict[tuple[str, int], str],
    inter_id: str,
    flow: dict[str, Any],
    allow_dir8_fallback_link: bool,
) -> FlowMapping:
    f_dir8_no = normalize_dir8_no(flow.get("f_dir8_no"))
    dir8_no = f_dir8_no
    link_id = str(flow.get("from_link_id") or "")
    if not link_id and dir8_no is not None:
        link_id = link_by_inter_dir.get((inter_id, dir8_no), "")
    if not link_id and allow_dir8_fallback_link and f_dir8_no is not None:
        link_id = f"dir8:{f_dir8_no}"
    return FlowMapping(
        link_id=link_id,
        turn_dir_no=_standard_turn_from_flow_type(flow.get("flow_type_no")),
    )


def _iter_split_seconds(start: datetime, end: datetime) -> tuple[int, datetime, float]:
    cursor = start
    while cursor < end:
        bucket_start = _bucket_start(cursor)
        bucket_end = bucket_start + timedelta(minutes=5)
        split_end = min(end, bucket_end)
        yield _step_index(bucket_start), bucket_start, (split_end - cursor).total_seconds()
        cursor = split_end


def _stage_offset_seconds(stage: dict[str, Any], period_start: datetime, fallback: int) -> int:
    stage_start = _parse_datetime(stage.get("stage_start_time"))
    if stage_start is None:
        return fallback
    return max(0, int((stage_start - period_start).total_seconds()))


def _add_color_interval(
    buckets: dict[tuple[date, str, str, int, int], BucketValue],
    *,
    inter_id: str,
    inter_name: str,
    link_id: str,
    turn_dir_no: int,
    color: str,
    start: datetime,
    end: datetime,
    cycle_len_sec: int,
    plan_no: int | None,
    ctrl_mode: str | None,
    data_source_no: int | None,
    period_start: datetime,
) -> None:
    if end <= start:
        return
    for step_index, bucket_start, seconds in _iter_split_seconds(start, end):
        key = (bucket_start.date(), inter_id, link_id, turn_dir_no, step_index)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = BucketValue(
                inter_id=inter_id,
                inter_name=inter_name,
                link_id=link_id,
                turn_dir_no=turn_dir_no,
                bucket_date=bucket_start.date(),
                day_of_week=_day_of_week(bucket_start),
                step_index=step_index,
            )
            buckets[key] = bucket
        bucket.add_seconds(
            color=color,
            seconds=seconds,
            cycle_len_sec=cycle_len_sec,
            plan_no=plan_no,
            ctrl_mode=ctrl_mode,
            data_source_no=data_source_no,
            period_start=period_start,
        )


def _add_param_sample_to_bucket(
    buckets: dict[tuple[date, str, str, int, int], BucketValue],
    *,
    inter_id: str,
    inter_name: str,
    link_id: str,
    turn_dir_no: int,
    bucket_start: datetime,
    green_exec_sec: float,
    yellow_exec_sec: float,
    all_red_exec_sec: float,
    cycle_len_sec: int,
    plan_no: int | None,
    ctrl_mode: str | None,
    data_source_no: int | None,
    period_start: datetime,
) -> None:
    step_index = _step_index(bucket_start)
    key = (bucket_start.date(), inter_id, link_id, turn_dir_no, step_index)
    bucket = buckets.get(key)
    if bucket is None:
        bucket = BucketValue(
            inter_id=inter_id,
            inter_name=inter_name,
            link_id=link_id,
            turn_dir_no=turn_dir_no,
            bucket_date=bucket_start.date(),
            day_of_week=_day_of_week(bucket_start),
            step_index=step_index,
        )
        buckets[key] = bucket
    bucket.add_param_sample(
        green_exec_sec=green_exec_sec,
        yellow_exec_sec=yellow_exec_sec,
        all_red_exec_sec=all_red_exec_sec,
        cycle_len_sec=cycle_len_sec,
        plan_no=plan_no,
        ctrl_mode=ctrl_mode,
        data_source_no=data_source_no,
        period_start=period_start,
    )


def _process_period_row(
    row: dict[str, Any],
    *,
    mappings: dict[tuple[str, int, str, str], FlowMapping],
    buckets: dict[tuple[date, str, str, int, int], BucketValue],
    allow_dir8_fallback_link: bool,
) -> dict[str, int]:
    counts = defaultdict(int)
    period_start = _parse_datetime(row.get("period_start_time"))
    period_end = _parse_datetime(row.get("period_end_time"))
    if period_start is None or period_end is None or period_end <= period_start:
        counts["invalid_period_rows"] += 1
        return counts

    inter_id = str(row.get("inter_id") or "")
    inter_name = _extract_inter_name(row.get("remark"))
    plan_no = _to_int(row.get("plan_no"), default=None)
    ctrl_mode = str(row.get("ctrl_mode") or "") or None
    cycle_len_sec = _to_int(row.get("cycle_len_sec"), default=0) or 0
    data_source_no = _to_int(row.get("data_source_no"), default=None)
    stage_exec_rows = _parse_json(row.get("stage_exec_json"), [])
    stage_flow_rows = _parse_json(row.get("stage_flow_combo_json"), [])

    if not inter_id or cycle_len_sec <= 0 or not stage_exec_rows or not stage_flow_rows:
        counts["unusable_period_rows"] += 1
        return counts

    flows_by_seq: dict[int, list[dict[str, Any]]] = {}
    flows_by_stage_no: dict[int, list[dict[str, Any]]] = {}
    for flow_row in stage_flow_rows:
        flows = _parse_json(flow_row.get("flow_combo"), [])
        seq_no = _to_int(flow_row.get("stage_exec_seq_no"), default=None)
        stage_no = _to_int(flow_row.get("stage_no"), default=None)
        if seq_no is not None:
            flows_by_seq[seq_no] = flows
        if stage_no is not None:
            flows_by_stage_no[stage_no] = flows

    stage_defs: list[tuple[int, int, int, int, list[dict[str, Any]]]] = []
    fallback_offset = 0
    for stage in stage_exec_rows:
        seq_no = _to_int(stage.get("stage_exec_seq_no"), default=None)
        stage_no = _to_int(stage.get("stage_no"), default=None)
        green_sec = _to_int(stage.get("green_exec_sec"), default=0) or 0
        yellow_sec = _to_int(stage.get("yellow_exec_sec"), default=0) or 0
        all_red_sec = _to_int(stage.get("all_red_exec_sec"), default=0) or 0
        stage_len_sec = _to_int(stage.get("stage_exec_len_sec"), default=0) or 0
        stage_len_sec = stage_len_sec or green_sec + yellow_sec + all_red_sec
        offset_sec = _stage_offset_seconds(stage, period_start, fallback_offset)
        fallback_offset += stage_len_sec
        flows = flows_by_seq.get(seq_no or -1) or flows_by_stage_no.get(stage_no or -1) or []
        if not flows or stage_len_sec <= 0:
            continue
        stage_defs.append((offset_sec, green_sec, yellow_sec, all_red_sec, flows))

    cycle_start = period_start
    while cycle_start < period_end:
        for offset_sec, green_sec, yellow_sec, all_red_sec, flows in stage_defs:
            stage_start = cycle_start + timedelta(seconds=offset_sec)
            green_end = stage_start + timedelta(seconds=green_sec)
            yellow_end = green_end + timedelta(seconds=yellow_sec)
            all_red_end = yellow_end + timedelta(seconds=all_red_sec)
            if stage_start >= period_end or all_red_end <= period_start:
                continue
            for flow in flows:
                mapping = _resolve_flow_mapping(
                    mappings=mappings,
                    inter_id=inter_id,
                    plan_no=plan_no,
                    flow=flow,
                    allow_dir8_fallback_link=allow_dir8_fallback_link,
                )
                if not mapping.link_id or mapping.turn_dir_no not in {1, 2, 3}:
                    counts["flow_without_link_or_turn"] += 1
                    continue
                _add_color_interval(
                    buckets,
                    inter_id=inter_id,
                    inter_name=inter_name,
                    link_id=mapping.link_id,
                    turn_dir_no=mapping.turn_dir_no,
                    color="green",
                    start=max(stage_start, period_start),
                    end=min(green_end, period_end),
                    cycle_len_sec=cycle_len_sec,
                    plan_no=plan_no,
                    ctrl_mode=ctrl_mode,
                    data_source_no=data_source_no,
                    period_start=period_start,
                )
                _add_color_interval(
                    buckets,
                    inter_id=inter_id,
                    inter_name=inter_name,
                    link_id=mapping.link_id,
                    turn_dir_no=mapping.turn_dir_no,
                    color="yellow",
                    start=max(green_end, period_start),
                    end=min(yellow_end, period_end),
                    cycle_len_sec=cycle_len_sec,
                    plan_no=plan_no,
                    ctrl_mode=ctrl_mode,
                    data_source_no=data_source_no,
                    period_start=period_start,
                )
                _add_color_interval(
                    buckets,
                    inter_id=inter_id,
                    inter_name=inter_name,
                    link_id=mapping.link_id,
                    turn_dir_no=mapping.turn_dir_no,
                    color="all_red",
                    start=max(yellow_end, period_start),
                    end=min(all_red_end, period_end),
                    cycle_len_sec=cycle_len_sec,
                    plan_no=plan_no,
                    ctrl_mode=ctrl_mode,
                    data_source_no=data_source_no,
                    period_start=period_start,
                )
                counts["expanded_flow_stage_rows"] += 1
        cycle_start += timedelta(seconds=cycle_len_sec)
    counts["processed_period_rows"] += 1
    return counts


def _fetch_period_rows(
    conn: Any,
    *,
    table_name: str,
    start_time: datetime,
    end_time: datetime,
) -> list[dict[str, Any]]:
    table_ident = _quote_identifier(table_name)
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
SELECT inter_id, period_start_time, period_end_time, cycle_len_sec,
       plan_no, ctrl_mode,
       CAST(stage_exec_json AS CHAR) AS stage_exec_json,
       CAST(stage_flow_combo_json AS CHAR) AS stage_flow_combo_json,
       data_source_no, remark
FROM {table_ident}
WHERE COALESCE(is_deleted, 0) = 0
  AND period_end_time > %s
  AND period_start_time < %s
ORDER BY inter_id, period_start_time
""".strip(),
            (start_time, end_time),
        )
        return list(cursor.fetchall())


def _fetch_schedule_source_rows(
    conn: Any,
    *,
    schedule_table: str = TABLE_SCHEDULE_CFG,
    day_period_table: str = TABLE_DAY_PLAN_PERIOD,
    plan_cfg_table: str = TABLE_PLAN_CFG,
    plan_stage_timing_table: str = TABLE_PLAN_STAGE_TIMING,
    stage_motor_flow_table: str = TABLE_STAGE_MOTOR_FLOW,
) -> list[dict[str, Any]]:
    schedule_ident = _quote_identifier(schedule_table)
    period_ident = _quote_identifier(day_period_table)
    plan_ident = _quote_identifier(plan_cfg_table)
    timing_ident = _quote_identifier(plan_stage_timing_table)
    flow_ident = _quote_identifier(stage_motor_flow_table)
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
SELECT sc.inter_id, sc.week_day_no, sc.schedule_no, sc.day_plan_no,
       pp.period_seq_no, pp.start_time, pp.end_time, pp.plan_no, pp.ctrl_mode,
       pc.plan_name, pc.cycle_len_sec,
       pst.stage_seq_no, pst.stage_no, pst.green_sec, pst.yellow_sec, pst.all_red_sec,
       smf.from_link_id, smf.f_dir8_no, smf.flow_type_no
FROM {schedule_ident} sc
JOIN {period_ident} pp
  ON pp.inter_id = sc.inter_id
 AND pp.day_plan_no = sc.day_plan_no
 AND COALESCE(pp.is_deleted, 0) = 0
JOIN {plan_ident} pc
  ON pc.inter_id = pp.inter_id
 AND pc.plan_no = pp.plan_no
 AND COALESCE(pc.is_deleted, 0) = 0
JOIN {timing_ident} pst
  ON pst.inter_id = pp.inter_id
 AND pst.plan_no = pp.plan_no
 AND COALESCE(pst.is_deleted, 0) = 0
JOIN {flow_ident} smf
  ON smf.inter_id = pst.inter_id
 AND smf.stage_no = pst.stage_no
 AND COALESCE(smf.is_deleted, 0) = 0
WHERE COALESCE(sc.is_deleted, 0) = 0
ORDER BY sc.inter_id, sc.week_day_no, sc.schedule_no, pp.period_seq_no,
         pst.stage_seq_no, smf.flow_seq_no
""".strip()
        )
        return list(cursor.fetchall())


def _expanded_weekdays(
    row: dict[str, Any],
    explicit_weekdays_by_inter: dict[str, set[int]],
) -> list[int]:
    inter_id = str(row.get("inter_id") or "")
    week_day_no = _to_int(row.get("week_day_no"), default=None)
    if week_day_no in {1, 2, 3, 4, 5, 6, 7}:
        return [week_day_no]
    if explicit_weekdays_by_inter.get(inter_id):
        return []
    return [1, 2, 3, 4, 5, 6, 7]


def _build_schedule_period_groups(rows: list[dict[str, Any]]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    explicit_weekdays_by_inter: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        week_day_no = _to_int(row.get("week_day_no"), default=None)
        if week_day_no in {1, 2, 3, 4, 5, 6, 7}:
            explicit_weekdays_by_inter[str(row.get("inter_id") or "")].add(week_day_no)

    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for day_of_week in _expanded_weekdays(row, explicit_weekdays_by_inter):
            key = (
                str(row.get("inter_id") or ""),
                day_of_week,
                _to_int(row.get("schedule_no"), default=0) or 0,
                _to_int(row.get("day_plan_no"), default=0) or 0,
                _to_int(row.get("period_seq_no"), default=0) or 0,
                _time_to_seconds(row.get("start_time")) or 0,
                _time_to_seconds(row.get("end_time")) or 0,
                _to_int(row.get("plan_no"), default=0) or 0,
            )
            groups[key].append(row)
    return groups


def _process_schedule_group(
    key: tuple[Any, ...],
    rows: list[dict[str, Any]],
    *,
    link_by_inter_dir: dict[tuple[str, int], str],
    buckets: dict[tuple[date, str, str, int, int], BucketValue],
    allow_dir8_fallback_link: bool,
) -> dict[str, int]:
    counts = defaultdict(int)
    if not rows:
        return counts
    inter_id, day_of_week, _, _, _, start_sec, end_sec, plan_no = key
    if not inter_id or start_sec == end_sec:
        counts["invalid_schedule_periods"] += 1
        return counts
    if end_sec <= start_sec:
        end_sec += 86400

    first = rows[0]
    cycle_len_sec = _to_int(first.get("cycle_len_sec"), default=0) or 0
    if cycle_len_sec <= 0:
        counts["invalid_schedule_periods"] += 1
        return counts

    inter_name = _extract_inter_name_from_plan_name(first.get("plan_name"))
    ctrl_mode = str(first.get("ctrl_mode") or "") or None
    period_start = BASE_WEEK_START + timedelta(days=int(day_of_week) - 1, seconds=int(start_sec))
    period_end = BASE_WEEK_START + timedelta(days=int(day_of_week) - 1, seconds=int(end_sec))

    stage_rows: dict[int, dict[str, Any]] = {}
    stage_flows: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        stage_seq_no = _to_int(row.get("stage_seq_no"), default=0) or 0
        stage_no = _to_int(row.get("stage_no"), default=None)
        if stage_no is None:
            continue
        stage_rows.setdefault(
            stage_seq_no,
            {
                "stage_no": stage_no,
                "green_sec": _to_int(row.get("green_sec"), default=0) or 0,
                "yellow_sec": _to_int(row.get("yellow_sec"), default=0) or 0,
                "all_red_sec": _to_int(row.get("all_red_sec"), default=0) or 0,
            },
        )
        stage_flows[stage_seq_no].append(
            {
                "from_link_id": row.get("from_link_id"),
                "f_dir8_no": row.get("f_dir8_no"),
                "flow_type_no": row.get("flow_type_no"),
            }
        )

    stage_defs: list[tuple[int, int, int, int, list[dict[str, Any]]]] = []
    offset_sec = 0
    for stage_seq_no in sorted(stage_rows):
        stage = stage_rows[stage_seq_no]
        green_sec = stage["green_sec"]
        yellow_sec = stage["yellow_sec"]
        all_red_sec = stage["all_red_sec"]
        stage_len_sec = green_sec + yellow_sec + all_red_sec
        flows = stage_flows.get(stage_seq_no) or []
        if stage_len_sec > 0 and flows:
            stage_defs.append((offset_sec, green_sec, yellow_sec, all_red_sec, flows))
        offset_sec += stage_len_sec

    movement_params: dict[tuple[str, int], dict[str, float]] = {}
    for _, green_sec, yellow_sec, all_red_sec, flows in stage_defs:
        seen_stage_movements: set[tuple[str, int]] = set()
        for flow in flows:
            mapping = _resolve_schedule_flow_mapping(
                link_by_inter_dir=link_by_inter_dir,
                inter_id=str(inter_id),
                flow=flow,
                allow_dir8_fallback_link=allow_dir8_fallback_link,
            )
            if not mapping.link_id or mapping.turn_dir_no not in {1, 2, 3}:
                counts["flow_without_link_or_turn"] += 1
                continue
            movement_key = (mapping.link_id, mapping.turn_dir_no)
            if movement_key in seen_stage_movements:
                continue
            seen_stage_movements.add(movement_key)
            entry = movement_params.setdefault(
                movement_key,
                {
                    "green_exec_sec": 0.0,
                    "yellow_exec_sec": 0.0,
                    "all_red_exec_sec": 0.0,
                },
            )
            entry["green_exec_sec"] += green_sec
            entry["yellow_exec_sec"] = max(entry["yellow_exec_sec"], yellow_sec)
            entry["all_red_exec_sec"] = max(entry["all_red_exec_sec"], all_red_sec)
            counts["expanded_flow_stage_rows"] += 1

    bucket_starts = {
        bucket_start for _, bucket_start, _ in _iter_split_seconds(period_start, period_end)
    }
    for (link_id, turn_dir_no), params in movement_params.items():
        for bucket_start in bucket_starts:
            _add_param_sample_to_bucket(
                buckets,
                inter_id=str(inter_id),
                inter_name=inter_name,
                link_id=link_id,
                turn_dir_no=turn_dir_no,
                bucket_start=bucket_start,
                green_exec_sec=params["green_exec_sec"],
                yellow_exec_sec=params["yellow_exec_sec"],
                all_red_exec_sec=params["all_red_exec_sec"],
                cycle_len_sec=cycle_len_sec,
                plan_no=int(plan_no) if plan_no else None,
                ctrl_mode=ctrl_mode,
                data_source_no=2,
                period_start=period_start,
            )
    counts["processed_schedule_periods"] += 1
    return counts


def _aggregate_buckets_to_rows(
    buckets: dict[tuple[date, str, str, int, int], BucketValue],
) -> list[dict[str, Any]]:
    """先按选中 plan_no 聚合，再为目标主键挑选与 plan_no 一致的一组参数。"""
    historic_by_plan: dict[tuple[str, str, int, int, int, int | None], HistoricAgg] = {}
    for bucket in buckets.values():
        selected_stats = bucket.selected_plan_stats()
        if selected_stats is None:
            continue
        key = (
            bucket.inter_id,
            bucket.link_id,
            bucket.turn_dir_no,
            bucket.day_of_week,
            bucket.step_index,
            selected_stats.plan_no,
        )
        agg = historic_by_plan.get(key)
        if agg is None:
            agg = HistoricAgg(
                inter_id=bucket.inter_id,
                inter_name=bucket.inter_name,
                link_id=bucket.link_id,
                turn_dir_no=bucket.turn_dir_no,
                day_of_week=bucket.day_of_week,
                step_index=bucket.step_index,
            )
            historic_by_plan[key] = agg
        agg.add_bucket(bucket)

    selected_by_target_key: dict[tuple[str, str, int, int, int], HistoricAgg] = {}
    for agg in historic_by_plan.values():
        key = (agg.inter_id, agg.link_id, agg.turn_dir_no, agg.day_of_week, agg.step_index)
        current = selected_by_target_key.get(key)
        if current is None or (
            (agg.latest_period_start or datetime.min, agg.sample_count, agg.plan_no or 0)
            >= (
                current.latest_period_start or datetime.min,
                current.sample_count,
                current.plan_no or 0,
            )
        ):
            selected_by_target_key[key] = agg

    rows = [agg.to_row() for agg in selected_by_target_key.values()]
    rows.sort(
        key=lambda item: (
            item["inter_id"],
            item["link_id"],
            item["turn_dir_no"],
            item["day_of_week"],
            item["step_index"],
        )
    )
    return rows


def build_turn_5min_rows_from_schedule(
    conn: Any,
    *,
    mapping_table: str = TABLE_ATOM_LANE_MAPPING,
    allow_dir8_fallback_link: bool = False,
    fill_link_id_from_pg: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ensure_atom_lane_mapping_extensions(conn, mapping_table)
    extension_counts: dict[str, int] = {}
    if fill_link_id_from_pg:
        extension_counts = fill_atom_mapping_link_id_from_pg(conn, mapping_table)

    link_by_inter_dir = _load_unique_link_by_inter_dir(conn, mapping_table)
    source_rows = _fetch_schedule_source_rows(conn)
    period_groups = _build_schedule_period_groups(source_rows)
    buckets: dict[tuple[date, str, str, int, int], BucketValue] = {}
    counts: dict[str, int] = {
        "source_schedule_rows": len(source_rows),
        "schedule_period_groups": len(period_groups),
        "unique_link_dir_mappings": len(link_by_inter_dir),
        **extension_counts,
    }
    for key, rows in period_groups.items():
        row_counts = _process_schedule_group(
            key,
            rows,
            link_by_inter_dir=link_by_inter_dir,
            buckets=buckets,
            allow_dir8_fallback_link=allow_dir8_fallback_link,
        )
        for count_key, value in row_counts.items():
            counts[count_key] = counts.get(count_key, 0) + value

    rows = _aggregate_buckets_to_rows(buckets)
    counts["date_bucket_rows"] = len(buckets)
    counts["target_rows"] = len(rows)
    return rows, counts


def build_turn_5min_rows(
    conn: Any,
    *,
    source_table: str = TABLE_PERIOD_PLAN_EXEC_HIS,
    mapping_table: str = TABLE_ATOM_LANE_MAPPING,
    start_time: datetime,
    end_time: datetime,
    allow_dir8_fallback_link: bool = False,
    fill_link_id_from_pg: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ensure_atom_lane_mapping_extensions(conn, mapping_table)
    extension_counts: dict[str, int] = {}
    if fill_link_id_from_pg:
        extension_counts = fill_atom_mapping_link_id_from_pg(conn, mapping_table)
    mappings = _load_flow_mappings(conn, mapping_table)
    period_rows = _fetch_period_rows(
        conn,
        table_name=source_table,
        start_time=start_time,
        end_time=end_time,
    )

    buckets: dict[tuple[date, str, str, int, int], BucketValue] = {}
    counts: dict[str, int] = {
        "source_period_rows": len(period_rows),
        "mapping_rows": len(mappings),
        **extension_counts,
    }
    for row in period_rows:
        row_counts = _process_period_row(
            row,
            mappings=mappings,
            buckets=buckets,
            allow_dir8_fallback_link=allow_dir8_fallback_link,
        )
        for key, value in row_counts.items():
            counts[key] = counts.get(key, 0) + value

    rows = _aggregate_buckets_to_rows(buckets)
    counts["date_bucket_rows"] = len(buckets)
    counts["target_rows"] = len(rows)
    return rows, counts


def _build_upsert_sql(table_name: str) -> str:
    quoted_columns = ", ".join(_quote_identifier(col) for col in TARGET_COLUMNS)
    placeholders = ", ".join(["%s"] * len(TARGET_COLUMNS))
    update_columns = [
        col
        for col in TARGET_COLUMNS
        if col not in {"inter_id", "link_id", "turn_dir_no", "day_of_week", "step_index"}
    ]
    update_clause = ", ".join(
        f"{_quote_identifier(col)}=VALUES({_quote_identifier(col)})" for col in update_columns
    )
    update_clause += ", `update_time`=CURRENT_TIMESTAMP"
    return (
        f"INSERT INTO {_quote_identifier(table_name)} ({quoted_columns}) "
        f"VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
    )


def upsert_rows(conn: Any, rows: list[dict[str, Any]], *, target_table: str) -> int:
    if not rows:
        return 0
    _ensure_target_table(conn, target_table)
    sql = _build_upsert_sql(target_table)
    values = [tuple(row.get(col) for col in TARGET_COLUMNS) for row in rows]
    with conn.cursor() as cursor:
        cursor.executemany(sql, values)
    conn.commit()
    return len(rows)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TARGET_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _default_start_time(weeks: int) -> datetime:
    return datetime.combine(datetime.now().date(), time.min) - timedelta(weeks=weeks)


def main() -> None:
    try:
        from env import load_project_env

        load_project_env()
    except ModuleNotFoundError:
        pass

    parser = argparse.ArgumentParser(description="生成路口历史配时参数聚合表")
    parser.add_argument(
        "--source-mode",
        choices=("schedule", "period-history"),
        default="schedule",
        help="schedule=从调度时段计划标准表推导；period-history=从时段执行历史表聚合",
    )
    parser.add_argument("--source-table", default=TABLE_PERIOD_PLAN_EXEC_HIS)
    parser.add_argument("--mapping-table", default=TABLE_ATOM_LANE_MAPPING)
    parser.add_argument("--target-table", default=TABLE_TARGET)
    parser.add_argument("--weeks", type=int, default=12, help="默认聚合最近 N 周")
    parser.add_argument("--start-time", help="聚合开始时间，格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--end-time", help="聚合结束时间，格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--output-csv", type=Path, help="可选：写出聚合结果 CSV")
    parser.add_argument("--skip-db", action="store_true", help="仅计算/导出，不写入 MySQL")
    parser.add_argument(
        "--allow-dir8-fallback-link",
        action="store_true",
        help="link_id 缺失时临时使用 dir8:{f_dir8_no}，仅用于调试验证",
    )
    parser.add_argument(
        "--fill-link-id-from-pg",
        action="store_true",
        help="按 PG 渠化宽表将各进口方向统一为主路 link_id 写入 signal_atom_lane_mapping",
    )
    args = parser.parse_args()

    start_time = _parse_datetime(args.start_time) if args.start_time else _default_start_time(args.weeks)
    end_time = _parse_datetime(args.end_time) if args.end_time else datetime.now()
    if start_time is None or end_time is None or end_time <= start_time:
        raise ValueError("聚合时间范围无效")

    conn = _get_mysql_connection(streaming=False)
    try:
        if args.source_mode == "schedule":
            rows, counts = build_turn_5min_rows_from_schedule(
                conn,
                mapping_table=args.mapping_table,
                allow_dir8_fallback_link=args.allow_dir8_fallback_link,
                fill_link_id_from_pg=args.fill_link_id_from_pg,
            )
        else:
            rows, counts = build_turn_5min_rows(
                conn,
                source_table=args.source_table,
                mapping_table=args.mapping_table,
                start_time=start_time,
                end_time=end_time,
                allow_dir8_fallback_link=args.allow_dir8_fallback_link,
                fill_link_id_from_pg=args.fill_link_id_from_pg,
            )
        if args.output_csv:
            write_csv(args.output_csv, rows)
            print(f"已写出 CSV: {args.output_csv}")
        if not args.skip_db:
            counts["upsert_rows"] = upsert_rows(conn, rows, target_table=args.target_table)
        for key in sorted(counts):
            print(f"{key}: {counts[key]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
