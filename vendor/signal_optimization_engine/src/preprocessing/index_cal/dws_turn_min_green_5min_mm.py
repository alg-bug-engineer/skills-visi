#!/usr/bin/env python3
"""生成评价用进口转向车流最小绿表 dws_turn_min_green_5min_mm。

数据来源（海信原始配时方案解析后的 DWD 标准表）：
  - dwd_ctl_inter_schedule_cfg / dwd_ctl_inter_day_plan_period：星期几 + 时段 → plan_no
  - dwd_ctl_inter_plan_cfg：周期长度
  - dwd_ctl_inter_plan_stage_timing：阶段计划绿灯
  - dwd_ctl_inter_stage_cfg：阶段交通流组合（含行人 flow_type_no=5）
  - dwd_ctl_inter_stage_motor_flow_rltn：阶段机动车流 → link_id + turn_dir_no

定位说明：
  本表只用于评价链路（如转向绿灯利用率），不作为优化器阶段最小绿/最大绿约束来源。

最小绿计算口径（与 preprocessing.timing.stage_min_green 行人过街时间一致）：
  - 阶段无行人跟随放行：min_green = 14s
  - 阶段有行人跟随放行：min_green = max(行人安全过街时间, 14s)
    行人安全过街时间 = ceil(进口车道数 + 出口车道数) × 3.25m ÷ 1.2m/s
  - 同一转向跨多个阶段放行时，min_green 取各阶段最小绿的最大值（保守约束）；
    green_time_plan 取各阶段计划绿灯之和（与历史配时聚合口径一致）。
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from preprocessing.timing.dir8_encoding import normalize_dir8_no
from data.mysql_reader import _crossing_lanes_by_dir
from preprocessing.index_cal.inter_turn_5min_his_mm import (
    BASE_WEEK_START,
    TABLE_ATOM_LANE_MAPPING,
    TABLE_PLAN_CFG,
    TABLE_PLAN_STAGE_TIMING,
    TABLE_STAGE_MOTOR_FLOW,
    _build_schedule_period_groups,
    _extract_inter_name_from_plan_name,
    _fetch_schedule_source_rows,
    _iter_split_seconds,
    _load_unique_link_by_inter_dir,
    _resolve_schedule_flow_mapping,
    _standard_turn_from_flow_type,
    _to_int,
    ensure_atom_lane_mapping_extensions,
)
from preprocessing.timing.stage_min_green import (
    DEFAULT_MOTOR_MIN_GREEN_S,
    pedestrian_min_green_s,
)
from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_STAGE_CFG = "dwd_ctl_inter_stage_cfg"
TABLE_TARGET = "dws_turn_min_green_5min_mm"

PEDESTRIAN_FLOW_TYPE_NO = 5

TARGET_COLUMNS = [
    "inter_id",
    "link_id",
    "turn_dir_no",
    "day_of_week",
    "step_index",
    "inter_name",
    "dir8_code",
    "dir4_code",
    "plan_no",
    "cycle_len_sec",
    "green_time_plan",
    "min_green_time",
    "has_pedestrian",
    "is_deleted",
]


def _create_table_ddl(table_name: str) -> str:
    table_ident = _quote_identifier(table_name)
    return f"""
CREATE TABLE IF NOT EXISTS {table_ident} (
    `inter_id`          VARCHAR(16)  NOT NULL COMMENT '路口ID，16位标准编码',
    `link_id`           VARCHAR(32)  NOT NULL COMMENT '进口道路段ID，唯一标识一个进口道',
    `turn_dir_no`       TINYINT      NOT NULL COMMENT '转向类型：1-左转（含调头），2-直行，3-右转',
    `day_of_week`       TINYINT      NOT NULL COMMENT '星期几：1-周一，2-周二，3-周三，4-周四，5-周五，6-周六，7-周日',
    `step_index`        SMALLINT     NOT NULL COMMENT '5分钟时间片序号，取值0~287，对应全天288个5分钟窗口',
    `inter_name`        VARCHAR(128) DEFAULT NULL COMMENT '路口名称，便于直观识别',
    `dir8_code`         INT          DEFAULT NULL COMMENT '八方向编码：0-北，1-东北，2-东，3-东南，4-南，5-西南，6-西，7-西北',
    `dir4_code`         INT          DEFAULT NULL COMMENT '四方向编码：0-北，1-东，2-南，3-西',
    `plan_no`           INT          NOT NULL COMMENT '配时方案号，关联自信号离线多时段方案表 ods_ctl_inter_schedule_period_raw.plan_no',
    `cycle_len_sec`     INT          NOT NULL COMMENT '当前方案周期长度（秒），来源于信号离线多时段方案表',
    `green_time_plan`   DECIMAL(8,1) NOT NULL COMMENT '当前方案该转向对应相位的计划绿灯时长（秒），来源于 dwd_ctl_inter_plan_stage_timing',
    `min_green_time`    DECIMAL(8,1) NOT NULL COMMENT '满足车流通行的理论最小绿灯时长（秒），综合考虑固定下限比例和行人跟随放行的最低时长需求后计算得出',
    `has_pedestrian`    TINYINT      NOT NULL COMMENT '同相位是否有行人跟随放行标志：0-无行人放行，1-有行人放行',
    `create_time`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `update_time`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    `is_deleted`        TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除标记：0-有效，1-已删除',
    PRIMARY KEY (`inter_id`, `link_id`, `turn_dir_no`, `day_of_week`, `step_index`),
    INDEX `idx_inter_id` (`inter_id`) COMMENT '按路口维度查询加速',
    INDEX `idx_inter_id_day_step` (`inter_id`, `day_of_week`, `step_index`) COMMENT '按路口+星期+时间片联合查询加速',
    INDEX `idx_turn_dir_no` (`turn_dir_no`) COMMENT '按转向类型筛选加速',
    INDEX `idx_plan_no` (`plan_no`) COMMENT '按配时方案号查询加速',
    INDEX `idx_min_green_low` (`min_green_time`) COMMENT '按最小绿灯时长查询加速，便于筛选绿灯空放转向',
    INDEX `idx_has_pedestrian` (`has_pedestrian`) COMMENT '按行人跟随放行标志筛选加速'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='路口进口转向车流最小绿表 - 按进口道+转向+星期几+5分钟时间片，基于信号离线多时段方案表计算满足车流通行的理论最小绿灯时长'
""".strip()


def ensure_target_table(conn: Any, table_name: str = TABLE_TARGET) -> None:
    with conn.cursor() as cursor:
        cursor.execute(_create_table_ddl(table_name))
    conn.commit()


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


def _dir4_from_dir8(dir8_code: int) -> int:
    return dir8_code // 2


def load_link_dir_codes(inter_ids: set[str]) -> dict[tuple[str, str], dict[str, int]]:
    if not inter_ids:
        return {}
    from data.pg_reader import connect_pg, fetch_channelization

    mapping: dict[tuple[str, str], dict[str, int]] = {}
    pg_conn = connect_pg()
    try:
        for inter_id in sorted(inter_ids):
            channelization = fetch_channelization(pg_conn, inter_id)
            for approach in channelization.get("approaches") or []:
                link_id = str(approach.get("linkId") or "").strip()
                dir8_code = _to_int(approach.get("dir8Code"), default=None)
                if not link_id or dir8_code is None or dir8_code not in range(0, 8):
                    continue
                mapping[(inter_id, link_id)] = {
                    "dir8_code": dir8_code,
                    "dir4_code": _dir4_from_dir8(dir8_code),
                }
    finally:
        pg_conn.close()
    return mapping


def compute_stage_min_green_s(
    flow_combo: list[dict[str, Any]],
    crossing_lanes_by_dir: dict[int, int],
) -> tuple[float, bool]:
    """计算单个阶段最小绿（秒）及是否含行人跟随放行."""
    ped_dirs: list[int] = []
    for flow in flow_combo:
        if _to_int(flow.get("flow_type_no"), default=-1) != PEDESTRIAN_FLOW_TYPE_NO:
            continue
        dir8_no = normalize_dir8_no(flow.get("f_dir8_no"))
        if dir8_no is not None:
            ped_dirs.append(dir8_no)

    if not ped_dirs:
        return float(DEFAULT_MOTOR_MIN_GREEN_S), False

    ped_mins: list[int] = []
    for dir8_no in ped_dirs:
        lanes = crossing_lanes_by_dir.get(dir8_no)
        if lanes and lanes > 0:
            ped_mins.append(pedestrian_min_green_s(lanes))
        else:
            ped_mins.append(DEFAULT_MOTOR_MIN_GREEN_S)
    return float(max(max(ped_mins), DEFAULT_MOTOR_MIN_GREEN_S)), True


@dataclass
class TurnPlanMetrics:
    plan_no: int
    cycle_len_sec: int
    green_time_plan: float = 0.0
    min_green_time: float = float(DEFAULT_MOTOR_MIN_GREEN_S)
    has_pedestrian: int = 0


@dataclass
class PlanContext:
    inter_id: str
    plan_no: int
    plan_name: str
    cycle_len_sec: int
    stage_green: dict[int, int] = field(default_factory=dict)
    stage_flow_combo: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    stage_motor_flows: dict[int, list[dict[str, Any]]] = field(default_factory=dict)


def _load_plan_contexts(conn: Any) -> dict[tuple[str, int], PlanContext]:
    contexts: dict[tuple[str, int], PlanContext] = {}
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
SELECT inter_id, plan_no, plan_name, cycle_len_sec
FROM {_quote_identifier(TABLE_PLAN_CFG)}
WHERE COALESCE(is_deleted, 0) = 0
""".strip()
        )
        for row in cursor.fetchall():
            inter_id = str(row.get("inter_id") or "")
            plan_no = _to_int(row.get("plan_no"), default=None)
            if not inter_id or plan_no is None:
                continue
            contexts[(inter_id, plan_no)] = PlanContext(
                inter_id=inter_id,
                plan_no=plan_no,
                plan_name=str(row.get("plan_name") or ""),
                cycle_len_sec=_to_int(row.get("cycle_len_sec"), default=0) or 0,
            )

        cursor.execute(
            f"""
SELECT inter_id, plan_no, stage_no, green_sec
FROM {_quote_identifier(TABLE_PLAN_STAGE_TIMING)}
WHERE COALESCE(is_deleted, 0) = 0
""".strip()
        )
        for row in cursor.fetchall():
            key = (str(row.get("inter_id") or ""), _to_int(row.get("plan_no"), default=0) or 0)
            ctx = contexts.get(key)
            if ctx is None:
                continue
            stage_no = _to_int(row.get("stage_no"), default=None)
            if stage_no is None:
                continue
            ctx.stage_green[stage_no] = _to_int(row.get("green_sec"), default=0) or 0

        cursor.execute(
            f"""
SELECT inter_id, stage_no, CAST(flow_combo_json AS CHAR) AS flow_combo_json
FROM {_quote_identifier(TABLE_STAGE_CFG)}
WHERE COALESCE(is_deleted, 0) = 0
""".strip()
        )
        for row in cursor.fetchall():
            inter_id = str(row.get("inter_id") or "")
            stage_no = _to_int(row.get("stage_no"), default=None)
            if not inter_id or stage_no is None:
                continue
            combo = _parse_json(row.get("flow_combo_json"), [])
            for key, ctx in contexts.items():
                if key[0] != inter_id:
                    continue
                ctx.stage_flow_combo.setdefault(stage_no, combo)

        cursor.execute(
            f"""
SELECT inter_id, stage_no, from_link_id, f_dir8_no, flow_type_no
FROM {_quote_identifier(TABLE_STAGE_MOTOR_FLOW)}
WHERE COALESCE(is_deleted, 0) = 0
""".strip()
        )
        for row in cursor.fetchall():
            inter_id = str(row.get("inter_id") or "")
            stage_no = _to_int(row.get("stage_no"), default=None)
            if not inter_id or stage_no is None:
                continue
            for key, ctx in contexts.items():
                if key[0] != inter_id:
                    continue
                ctx.stage_motor_flows.setdefault(stage_no, []).append(row)
    return contexts


def _build_turn_metrics_for_plan(
    ctx: PlanContext,
    *,
    link_by_inter_dir: dict[tuple[str, int], str],
    crossing_lanes_by_dir: dict[int, int],
    allow_dir8_fallback_link: bool,
) -> dict[tuple[str, int], TurnPlanMetrics]:
    stage_min_green: dict[int, tuple[float, bool]] = {}
    for stage_no, flow_combo in ctx.stage_flow_combo.items():
        stage_min_green[stage_no] = compute_stage_min_green_s(flow_combo, crossing_lanes_by_dir)

    metrics: dict[tuple[str, int], TurnPlanMetrics] = {}
    for stage_no, flows in ctx.stage_motor_flows.items():
        min_green, has_ped = stage_min_green.get(
            stage_no,
            (float(DEFAULT_MOTOR_MIN_GREEN_S), False),
        )
        green_sec = float(ctx.stage_green.get(stage_no, 0))
        seen: set[tuple[str, int]] = set()
        for flow in flows:
            mapping = _resolve_schedule_flow_mapping(
                link_by_inter_dir=link_by_inter_dir,
                inter_id=ctx.inter_id,
                flow=flow,
                allow_dir8_fallback_link=allow_dir8_fallback_link,
            )
            turn_dir_no = mapping.turn_dir_no or _standard_turn_from_flow_type(flow.get("flow_type_no"))
            link_id = mapping.link_id
            if not link_id or turn_dir_no not in {1, 2, 3}:
                continue
            movement_key = (link_id, turn_dir_no)
            if movement_key in seen:
                continue
            seen.add(movement_key)
            entry = metrics.get(movement_key)
            if entry is None:
                entry = TurnPlanMetrics(
                    plan_no=ctx.plan_no,
                    cycle_len_sec=ctx.cycle_len_sec,
                )
                metrics[movement_key] = entry
            entry.green_time_plan += green_sec
            entry.min_green_time = max(entry.min_green_time, min_green)
            if has_ped:
                entry.has_pedestrian = 1
    return metrics


def _crossing_lanes_from_channelization(channel: dict[str, Any]) -> dict[int, int]:
    """渠化结构 → {0 基 dir8No: 进口+出口车道数}."""
    entry_by_dir: dict[int, int] = {}
    exit_by_dir: dict[int, int] = {}
    for approach in channel.get("approaches") or []:
        dir8_no = normalize_dir8_no(approach.get("dir8Code"))
        if dir8_no is None:
            continue
        lanes = _to_int(approach.get("laneTotal"), default=0) or 0
        if lanes <= 0:
            continue
        role = str(approach.get("linkRole") or "entrance")
        if role == "exit":
            exit_by_dir[dir8_no] = exit_by_dir.get(dir8_no, 0) + lanes
        else:
            entry_by_dir[dir8_no] = entry_by_dir.get(dir8_no, 0) + lanes
    out: dict[int, int] = {}
    for dir8_no in set(entry_by_dir) | set(exit_by_dir):
        total = entry_by_dir.get(dir8_no, 0) + exit_by_dir.get(dir8_no, 0)
        if total > 0:
            out[dir8_no] = total
    return out


def _crossing_lanes_for_inter(conn: Any, inter_id: str, cache: dict[str, dict[int, int]]) -> dict[int, int]:
    cached = cache.get(inter_id)
    if cached is not None:
        return cached

    lanes: dict[int, int] = {}
    try:
        from data.pg_reader import connect_pg, fetch_channelization

        pg_conn = connect_pg()
        try:
            channel = fetch_channelization(pg_conn, inter_id)
            if channel.get("approaches"):
                lanes = _crossing_lanes_from_channelization(channel)
        finally:
            pg_conn.close()
    except Exception:
        lanes = {}

    if not lanes:
        try:
            lanes = _crossing_lanes_by_dir(conn, inter_id)
        except Exception:
            lanes = {}

    cache[inter_id] = lanes
    return lanes


def build_turn_min_green_rows(
    conn: Any,
    *,
    mapping_table: str = TABLE_ATOM_LANE_MAPPING,
    allow_dir8_fallback_link: bool = False,
    fill_dir_from_pg: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ensure_atom_lane_mapping_extensions(conn, mapping_table)
    link_by_inter_dir = _load_unique_link_by_inter_dir(conn, mapping_table)
    plan_contexts = _load_plan_contexts(conn)
    source_rows = _fetch_schedule_source_rows(conn)
    period_groups = _build_schedule_period_groups(source_rows)

    crossing_cache: dict[str, dict[int, int]] = {}
    plan_metrics_cache: dict[tuple[str, int], dict[tuple[str, int], TurnPlanMetrics]] = {}
    target_rows_map: dict[tuple[str, str, int, int, int], dict[str, Any]] = {}
    counts: dict[str, int] = {
        "source_schedule_rows": len(source_rows),
        "schedule_period_groups": len(period_groups),
        "plan_contexts": len(plan_contexts),
        "unique_link_dir_mappings": len(link_by_inter_dir),
    }

    for key, rows in period_groups.items():
        inter_id, day_of_week, _, _, _, start_sec, end_sec, plan_no = key
        if not inter_id or start_sec == end_sec or not plan_no:
            counts["invalid_schedule_periods"] = counts.get("invalid_schedule_periods", 0) + 1
            continue
        if end_sec <= start_sec:
            end_sec += 86400

        ctx = plan_contexts.get((str(inter_id), int(plan_no)))
        if ctx is None or ctx.cycle_len_sec <= 0:
            counts["missing_plan_context"] = counts.get("missing_plan_context", 0) + 1
            continue

        cache_key = (ctx.inter_id, ctx.plan_no)
        if cache_key not in plan_metrics_cache:
            plan_metrics_cache[cache_key] = _build_turn_metrics_for_plan(
                ctx,
                link_by_inter_dir=link_by_inter_dir,
                crossing_lanes_by_dir=_crossing_lanes_for_inter(conn, ctx.inter_id, crossing_cache),
                allow_dir8_fallback_link=allow_dir8_fallback_link,
            )
        turn_metrics = plan_metrics_cache[cache_key]
        if not turn_metrics:
            counts["empty_plan_turn_metrics"] = counts.get("empty_plan_turn_metrics", 0) + 1
            continue

        first = rows[0] if rows else {}
        inter_name = _extract_inter_name_from_plan_name(first.get("plan_name") or ctx.plan_name)
        period_start = BASE_WEEK_START + timedelta(days=int(day_of_week) - 1, seconds=int(start_sec))
        period_end = BASE_WEEK_START + timedelta(days=int(day_of_week) - 1, seconds=int(end_sec))

        for (link_id, turn_dir_no), metrics in turn_metrics.items():
            for step_index, _, _ in _iter_split_seconds(period_start, period_end):
                row_key = (str(inter_id), link_id, turn_dir_no, int(day_of_week), step_index)
                target_rows_map[row_key] = {
                    "inter_id": str(inter_id),
                    "link_id": link_id,
                    "turn_dir_no": turn_dir_no,
                    "day_of_week": int(day_of_week),
                    "step_index": step_index,
                    "inter_name": inter_name or None,
                    "dir8_code": None,
                    "dir4_code": None,
                    "plan_no": int(plan_no),
                    "cycle_len_sec": metrics.cycle_len_sec,
                    "green_time_plan": round(metrics.green_time_plan, 1),
                    "min_green_time": round(metrics.min_green_time, 1),
                    "has_pedestrian": metrics.has_pedestrian,
                    "is_deleted": 0,
                }
        counts["processed_schedule_periods"] = counts.get("processed_schedule_periods", 0) + 1

    target_rows = list(target_rows_map.values())
    if fill_dir_from_pg and target_rows:
        inter_ids = {row["inter_id"] for row in target_rows}
        link_dir_codes = load_link_dir_codes(inter_ids)
        for row in target_rows:
            codes = link_dir_codes.get((row["inter_id"], row["link_id"]), {})
            row["dir8_code"] = codes.get("dir8_code")
            row["dir4_code"] = codes.get("dir4_code")
        counts["link_dir_mappings"] = len(link_dir_codes)

    target_rows.sort(
        key=lambda item: (
            item["inter_id"],
            item["link_id"],
            item["turn_dir_no"],
            item["day_of_week"],
            item["step_index"],
        )
    )
    counts["target_rows"] = len(target_rows)
    counts["distinct_plans"] = len(plan_metrics_cache)
    return target_rows, counts


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


def upsert_rows(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    target_table: str = TABLE_TARGET,
    batch_size: int = 2000,
) -> int:
    if not rows:
        return 0
    ensure_target_table(conn, target_table)
    sql = _build_upsert_sql(target_table)
    values = [tuple(row.get(col) for col in TARGET_COLUMNS) for row in rows]
    with conn.cursor() as cursor:
        for offset in range(0, len(values), batch_size):
            cursor.executemany(sql, values[offset : offset + batch_size])
    conn.commit()
    return len(rows)


def main() -> None:
    try:
        from env import load_project_env

        load_project_env()
    except ModuleNotFoundError:
        pass

    parser = argparse.ArgumentParser(description="生成路口进口转向车流最小绿表 dws_turn_min_green_5min_mm")
    parser.add_argument("--target-table", default=TABLE_TARGET)
    parser.add_argument("--mapping-table", default=TABLE_ATOM_LANE_MAPPING)
    parser.add_argument("--skip-db", action="store_true", help="仅建表/计算统计，不写入 MySQL")
    parser.add_argument(
        "--allow-dir8-fallback-link",
        action="store_true",
        help="link_id 缺失时临时使用 dir8:{f_dir8_no}，仅用于调试验证",
    )
    parser.add_argument(
        "--no-fill-dir-from-pg",
        action="store_true",
        help="不从 PG 渠化宽表回填 dir8_code / dir4_code",
    )
    args = parser.parse_args()

    conn = _get_mysql_connection(streaming=False)
    try:
        ensure_target_table(conn, args.target_table)
        rows, counts = build_turn_min_green_rows(
            conn,
            mapping_table=args.mapping_table,
            allow_dir8_fallback_link=args.allow_dir8_fallback_link,
            fill_dir_from_pg=not args.no_fill_dir_from_pg,
        )
        if not args.skip_db:
            counts["upsert_rows"] = upsert_rows(conn, rows, target_table=args.target_table)
        for key in sorted(counts):
            print(f"{key}: {counts[key]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
