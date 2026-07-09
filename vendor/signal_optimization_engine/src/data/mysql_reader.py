"""MySQL 数据读取：路口列表与信号相位相序方案，导出为优化器兼容 JSON。

数据来源（signalctl 库）：
    - dwd_ctl_inter_plan_cfg              配时方案（周期、协调阶段、相位差）及路口列表
    - 路口渠化信息表                      逐车道渠化（进口/出口、车道转向、车道类型；可选）
    - 路口信息表                          渠化关联用基础信息（可选，不存在时跳过）
    - dwd_ctl_inter_plan_stage_timing     方案内各阶段配时与相序
    - dwd_ctl_inter_stage_cfg             阶段放行交通流组合（flow_combo_json）
    - dwd_ctl_inter_day_plan_cfg          路口名称（remark 中“路口名称=...”）
    - dwd_ctl_inter_day_plan_period       日计划时段（plan_no 对应执行时段，
                                          供按方案时段统计流量）

编码约定（工程内统一 0 基，北=0..西北=7）：
    - f_dir8_no / dir8No / dir8_no / dir8Code（渠化 API）均为 0 基
    - flow_type_no 直=1/左=2/右=3/掉=4 → turnDirNo 掉=0/左=1/直=2/右=3
    - 行人(5)/其他(9) 不属于机动车转向，phaseDirInfoDTOList 跳过；
      行人流单独导出为各阶段 pedDirList（0 基方位），供最小绿计算

路口渠化信息表口径（与 PG 渠化宽表逐路口互验得出）：
    - cross_id = 路口信息表.id；与 dwd 表通过
      dwd.cross_id(海信 ID 补零) ↔ 路口信息表.control_crossroad_id 关联
    - dir 0 基 8 方向（北=0 东=2 南=4 西=6），entry_type 0=进口 1=出口
    - lane_num 自路缘（最外侧）向中心线递增
    - drive_dir 位掩码：直行=1 左转=2 右转=4 掉头=8
      （3=直左 5=直右 6=左右 7=直左右 10=左+掉 15=全向）
    - lane_type 0=普通机动车道；非 0 为公交/非机动等特殊车道
      （库内 drive_dir 恒为 15），不计入机动车转向统计
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import Any

from data.readers import write_json
from data.pg_reader import connect_pg, fetch_channelization, summarize_left_lane_kind
from data.approach_side_order import annotate_and_sort_approaches
from preprocessing.timing.atom_lane_mapping import (
    movement_key_for_atom,
    resolve_atom_lane_mapping,
)
from preprocessing.timing.lane_cluster import build_lane_groups, lane_group_key, summarize_lane_groups

from preprocessing.timing.dir8_encoding import (
    DIR4_LABELS,
    DIR8_LABELS,
    dir4_code_from_dir8_no,
    dir8_label,
    dir8_no_from_flow_combo_item,
    normalize_dir8_no,
)

# flow_type_no → turnDirNo（掉头=0，左转=1，直行=2，右转=3）
FLOW_TYPE_TO_TURN_DIR = {1: 2, 2: 1, 3: 3, 4: 0}
TURN_DIR_LABELS = {0: "掉头", 1: "左转", 2: "直行", 3: "右转"}

# 路口渠化信息表 drive_dir 位掩码
DRIVE_DIR_THROUGH = 1
DRIVE_DIR_LEFT = 2
DRIVE_DIR_RIGHT = 4
DRIVE_DIR_UTURN = 8

_NAME_PATTERN = re.compile(r"路口名称=([^;]+)")


def connect_mysql():
    """按 .env 中 MYSQL_* 配置建立连接（DictCursor）。"""
    try:
        import pymysql
        import pymysql.cursors
    except ModuleNotFoundError as exc:  # pragma: no cover - 运行时依赖提示
        raise RuntimeError(
            "缺少 pymysql 依赖，请执行: pip install -e '.[db]' 或 pip install pymysql"
        ) from exc

    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "signalctl"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def fetch_intersection_list(db) -> list[dict[str, Any]]:
    """读取路口列表：从 dwd_ctl_inter_plan_cfg 聚合有配时方案的路口。"""
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT inter_id,
                   MIN(cross_id) AS cross_id,
                   MIN(remark) AS remark,
                   COUNT(DISTINCT plan_no) AS plan_count
            FROM dwd_ctl_inter_plan_cfg
            WHERE is_deleted = 0
            GROUP BY inter_id
            ORDER BY inter_id
            """
        )
        plan_rows = cur.fetchall()

        cur.execute(
            """
            SELECT inter_id,
                   COUNT(DISTINCT stage_no) AS stage_count
            FROM dwd_ctl_inter_stage_cfg
            WHERE is_deleted = 0
            GROUP BY inter_id
            """
        )
        stage_counts = {row["inter_id"]: row["stage_count"] for row in cur.fetchall()}

        cur.execute(
            """
            SELECT inter_id, MIN(remark) AS remark
            FROM dwd_ctl_inter_day_plan_cfg
            WHERE is_deleted = 0
            GROUP BY inter_id
            """
        )
        day_plan_remarks = {row["inter_id"]: row["remark"] for row in cur.fetchall()}

    intersections: list[dict[str, Any]] = []
    for row in plan_rows:
        inter_id = row["inter_id"]
        cross_id = row.get("cross_id") or ""
        name = (
            _extract_name(day_plan_remarks.get(inter_id))
            or _extract_name(row.get("remark"))
            or cross_id
            or inter_id
        )
        intersections.append(
            {
                "interId": inter_id,
                "crossId": cross_id,
                "name": name,
                "planCount": row["plan_count"],
                "stageCount": stage_counts.get(inter_id, 0),
                "baseInfo": None,
            }
        )
    return intersections


def fetch_lane_channelization(db, inter_id: str) -> dict[str, Any]:
    """从 路口渠化信息表 读取一个路口的进口/出口渠化，解析为各方向逐车道信息。

    返回结构与 pg_reader.fetch_channelization 一致（approaches 内含
    dir8Code / dir4Code / turnLanes / lanes 等字段），供同一前端渠化逻辑消费。
    转向统计口径：合用车道对其服务的每个转向各计 1 条，掉头并入左转，
    特殊车道（lane_type≠0，公交/非机动等）不计入转向统计但保留在 lanes 中。
    出口车道（entry_type=1）仅计数 laneTotal，不导出车道明细。
    """
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT MIN(cross_id) AS cross_id
            FROM dwd_ctl_inter_plan_cfg
            WHERE is_deleted = 0 AND inter_id = %s
            """,
            (inter_id,),
        )
        row = cur.fetchone() or {}
        cross_no = _to_int(row.get("cross_id"))
        if cross_no is None:
            return {"interId": inter_id, "approaches": []}

        cur.execute(
            """
            SELECT q.dir, q.entry_type, q.lane_num, q.lane_type, q.drive_dir,
                   q.lane_len, q.name
            FROM `路口渠化信息表` q
            JOIN `路口信息表` b ON b.id = q.cross_id
            WHERE b.control_crossroad_id = %s AND q.entry_type IN (0, 1)
            ORDER BY q.dir, q.entry_type, q.lane_num
            """,
            (cross_no,),
        )
        rows = cur.fetchall()

    entry_by_dir: dict[int, list[dict[str, Any]]] = {}
    exit_by_dir: dict[int, list[dict[str, Any]]] = {}
    cross_name = ""
    for r in rows:
        dir8_no = normalize_dir8_no(r.get("dir"))
        if dir8_no is None:
            continue
        cross_name = cross_name or (r.get("name") or "")
        bucket = entry_by_dir if _to_int(r.get("entry_type")) == 0 else exit_by_dir
        bucket.setdefault(dir8_no, []).append(r)

    approaches = []
    for dir8_no in sorted(set(entry_by_dir) | set(exit_by_dir)):
        # lane_num 自外侧向中心线递增，倒序后与 PG lane_info（中心线向外）同向
        dir_rows = sorted(
            entry_by_dir.get(dir8_no, []),
            key=lambda r: _to_int(r.get("lane_num")) or 0,
            reverse=True,
        )
        turn_lanes = {"left": 0, "through": 0, "right": 0}
        lanes = []
        for r in dir_rows:
            drive_dir = _to_int(r.get("drive_dir")) or 0
            lane_type = _to_int(r.get("lane_type")) or 0
            turns = _drive_dir_turns(drive_dir) if lane_type == 0 else ()
            for turn in turns:
                turn_lanes[turn] += 1
            lanes.append(
                {
                    "laneNo": _to_int(r.get("lane_num")),
                    "laneType": lane_type,
                    "driveDir": drive_dir,
                    "turns": list(turns),
                    "gbName": _drive_dir_label(drive_dir) if lane_type == 0 else "特殊车道",
                }
            )
        exit_rows = sorted(
            exit_by_dir.get(dir8_no, []),
            key=lambda r: _to_int(r.get("lane_num")) or 0,
            reverse=True,
        )
        exit_lane_total = len(exit_rows)
        approaches.append(
            {
                "linkId": "",
                "linkRole": "entrance",
                "dir8Code": dir8_no,
                "dir8Label": dir8_label(dir8_no),
                "dir4Code": dir4_code_from_dir8_no(dir8_no),
                "dir4Label": DIR4_LABELS.get(dir4_code_from_dir8_no(dir8_no) or -1, ""),
                "laneTotal": len(lanes),
                "lanes": lanes,
                "turnLanes": turn_lanes,
                "leftLaneKind": summarize_left_lane_kind(lanes),
            }
        )
        if exit_lane_total:
            approaches.append(
                {
                    "linkId": "",
                    "linkRole": "exit",
                    "dir8Code": dir8_no,
                    "dir8Label": dir8_label(dir8_no),
                    "dir4Code": dir4_code_from_dir8_no(dir8_no),
                    "dir4Label": DIR4_LABELS.get(dir4_code_from_dir8_no(dir8_no) or -1, ""),
                    "laneTotal": exit_lane_total,
                    "lanes": [],
                    "turnLanes": {"left": 0, "through": 0, "right": 0},
                }
            )

    approaches = annotate_and_sort_approaches(approaches, center_lon=None, center_lat=None)
    return {"interId": inter_id, "interName": cross_name, "approaches": approaches}


def _drive_dir_turns(drive_dir: int) -> tuple[str, ...]:
    """drive_dir 位掩码 → 页面/优化器转向（掉头并入左转）。"""
    turns = []
    if drive_dir & (DRIVE_DIR_LEFT | DRIVE_DIR_UTURN):
        turns.append("left")
    if drive_dir & DRIVE_DIR_THROUGH:
        turns.append("through")
    if drive_dir & DRIVE_DIR_RIGHT:
        turns.append("right")
    return tuple(turns)


def _drive_dir_label(drive_dir: int) -> str:
    parts = []
    if drive_dir & DRIVE_DIR_UTURN:
        parts.append("掉头")
    if drive_dir & DRIVE_DIR_LEFT:
        parts.append("左转")
    if drive_dir & DRIVE_DIR_THROUGH:
        parts.append("直行")
    if drive_dir & DRIVE_DIR_RIGHT:
        parts.append("右转")
    return "/".join(parts) or "—"


def _table_columns(db, table_name: str) -> set[str]:
    with db.cursor() as cur:
        cur.execute(f"SHOW COLUMNS FROM `{table_name}`")
        return {row["Field"] if isinstance(row, dict) else row[0] for row in cur.fetchall()}


def _table_exists(db, table_name: str) -> bool:
    try:
        with db.cursor() as cur:
            cur.execute("SHOW TABLES LIKE %s", (table_name,))
            return cur.fetchone() is not None
    except Exception:
        return False


def fetch_phase_plan_request(
    db,
    inter_id: str,
    *,
    plan_no: int | None = None,
    prefer_lane_phase_mapping: bool = True,
) -> dict[str, Any]:
    """读取一个路口的相位相序方案，组织为单路口优化器输入结构。

    返回结构与 `optimize_intersection` 请求体兼容：
    顶层含 interId / phasePlanOfTimeList，每个方案含 phaseStageInfoList，
    每个阶段含 phaseDirInfoDTOList（dir8No / turnDirNo 已转换为优化器编码）。
    turnFlowTotal / laneCount 库内无流量渠化数据，导出为 0 / 1 占位，需自行填充。
    """
    with db.cursor() as cur:
        plan_columns = _table_columns(db, "dwd_ctl_inter_plan_cfg")
        optional_plan_selects = []
        for column in ("signal_atom_json", "movement_mapping_json", "parse_quality_json"):
            if column in plan_columns:
                optional_plan_selects.append(f"CAST({column} AS CHAR) AS {column}")
            else:
                optional_plan_selects.append(f"NULL AS {column}")
        if "schema_version" in plan_columns:
            optional_plan_selects.append("schema_version")
        else:
            optional_plan_selects.append("NULL AS schema_version")
        optional_plan_sql = ",\n                   ".join(optional_plan_selects)
        params: list[Any] = [inter_id]
        plan_filter = ""
        if plan_no is not None:
            plan_filter = " AND plan_no = %s"
            params.append(plan_no)
        cur.execute(
            f"""
            SELECT plan_no, plan_name, cycle_len_sec, coord_stage_no,
                   offset_sec, stage_cnt, remark,
                   {optional_plan_sql}
            FROM dwd_ctl_inter_plan_cfg
            WHERE is_deleted = 0 AND inter_id = %s{plan_filter}
            ORDER BY plan_no
            """,
            params,
        )
        plan_rows = cur.fetchall()

        cur.execute(
            """
            SELECT pst.plan_no, pst.stage_seq_no, pst.stage_no,
                   pst.green_sec, pst.yellow_sec, pst.all_red_sec,
                   pst.max_green_sec, pst.min_green_sec, pst.stage_total_sec,
                   sc.stage_name,
                   CAST(sc.flow_combo_json AS CHAR) AS flow_combo_json
            FROM dwd_ctl_inter_plan_stage_timing pst
            LEFT JOIN dwd_ctl_inter_stage_cfg sc
              ON sc.inter_id = pst.inter_id
             AND sc.stage_no = pst.stage_no
             AND sc.is_deleted = 0
            WHERE pst.is_deleted = 0 AND pst.inter_id = %s
            ORDER BY pst.plan_no, pst.stage_seq_no
            """,
            (inter_id,),
        )
        stage_rows = cur.fetchall()

        overlap_by_plan = _fetch_plan_overlap_structures(db, inter_id)

        cur.execute(
            """
            SELECT MIN(cross_id) AS cross_id, MIN(remark) AS remark
            FROM dwd_ctl_inter_day_plan_cfg
            WHERE is_deleted = 0 AND inter_id = %s
            """,
            (inter_id,),
        )
        info = cur.fetchone() or {}

    stages_by_plan: dict[int, list[dict[str, Any]]] = {}
    for row in stage_rows:
        stages_by_plan.setdefault(row["plan_no"], []).append(_stage_payload(row))

    lane_phase_by_plan_stage = (
        _fetch_lane_phase_dir_infos(db, inter_id, plan_no=plan_no)
        if prefer_lane_phase_mapping
        else {}
    )
    for current_plan_no, stages in stages_by_plan.items():
        by_stage = lane_phase_by_plan_stage.get(current_plan_no) or {}
        if not by_stage:
            continue
        for stage in stages:
            stage_no = _to_int(stage.get("stageNo"))
            if stage_no is None or stage_no not in by_stage:
                continue
            stage["phaseDirInfoDTOList"] = by_stage[stage_no]
            stage["phaseDirInfoSource"] = "dwd_ctl_inter_plan_lane_phase_mapping"

    phase_plan_list = []
    for row in plan_rows:
        stages = stages_by_plan.get(row["plan_no"], [])
        phase_plan_list.append(
            {
                "interId": inter_id,
                "phasePlanId": f"PLAN-{row['plan_no']}",
                "phasePlanName": row.get("plan_name") or f"方案{row['plan_no']}",
                "planNo": row["plan_no"],
                "cycleLenSec": row.get("cycle_len_sec") or 0,
                "coordStageNo": row.get("coord_stage_no") or 0,
                "offsetSec": row.get("offset_sec") or 0,
                "phaseStageInfoList": stages,
                "schemaVersion": row.get("schema_version"),
                "signalAtomJson": _json_loads(row.get("signal_atom_json"), {}),
                "movementMappingJson": _json_loads(row.get("movement_mapping_json"), {}),
                "parseQualityJson": _json_loads(row.get("parse_quality_json"), {}),
                "overlapStructure": overlap_by_plan.get(_to_int(row.get("plan_no"))),
            }
        )

    return {
        "interId": inter_id,
        "interName": _extract_name(info.get("remark")) or info.get("cross_id") or inter_id,
        "crossId": info.get("cross_id"),
        "phasePlanOfTimeList": phase_plan_list,
    }


def fetch_plan_periods(db, inter_id: str) -> dict[int, list[tuple[str, str]]]:
    """读取一个路口各配时方案(plan_no)的执行时段，供按时段统计流量。

    数据来自 dwd_ctl_inter_day_plan_period（日计划时段表）；同一 plan_no 在
    不同日计划/时段中出现时取并集并去重。

    返回: {plan_no: [("HH:MM", "HH:MM"), ...]}
    """
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT plan_no, start_time, end_time
            FROM dwd_ctl_inter_day_plan_period
            WHERE is_deleted = 0 AND inter_id = %s AND plan_no IS NOT NULL
            ORDER BY plan_no, start_time
            """,
            (inter_id,),
        )
        rows = cur.fetchall()

    periods: dict[int, list[tuple[str, str]]] = {}
    for row in rows:
        plan_no = _to_int(row.get("plan_no"))
        start = _time_to_hhmm(row.get("start_time"))
        end = _time_to_hhmm(row.get("end_time"))
        if plan_no is None or start is None or end is None or start == end:
            continue
        window = (start, end)
        bucket = periods.setdefault(plan_no, [])
        if window not in bucket:
            bucket.append(window)
    return periods


def fetch_day_plan_weekdays(db, inter_id: str, day_plan_no: int) -> list[int]:
    """读取一个日计划在调度表中对应的星期几列表（1=周一 … 7=周日）。"""
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT week_day_no
            FROM dwd_ctl_inter_schedule_cfg
            WHERE is_deleted = 0
              AND inter_id = %s
              AND day_plan_no = %s
              AND week_day_no BETWEEN 1 AND 7
            ORDER BY week_day_no
            """,
            (inter_id, day_plan_no),
        )
        rows = cur.fetchall()
    weekdays: list[int] = []
    for row in rows:
        day = _to_int(row.get("week_day_no"))
        if day is not None:
            weekdays.append(day)
    return weekdays


def _fetch_plan_overlap_structures(db, inter_id: str) -> dict[int, dict[str, Any]]:
    table_name = "dwd_ctl_inter_plan_overlap_cfg"
    if not _table_exists(db, table_name):
        return {}
    try:
        with db.cursor() as cur:
            cur.execute(
                f"""
                SELECT plan_no,
                       CAST(depth_terms_json AS CHAR) AS depth_terms_json,
                       CAST(ratio_groups_json AS CHAR) AS ratio_groups_json,
                       CAST(slice_stage_nos_json AS CHAR) AS slice_stage_nos_json,
                       CAST(structure_json AS CHAR) AS structure_json
                FROM `{table_name}`
                WHERE is_deleted = 0 AND inter_id = %s
                """,
                (inter_id,),
            )
            rows = cur.fetchall()
    except Exception:
        return {}
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        plan_no = _to_int(row.get("plan_no"))
        if plan_no is None:
            continue
        structure = _json_loads(row.get("structure_json"), {})
        if not isinstance(structure, dict):
            structure = {}
        structure.setdefault("depth_terms", _json_loads(row.get("depth_terms_json"), []))
        structure.setdefault("ratio_groups", _json_loads(row.get("ratio_groups_json"), []))
        structure.setdefault("slice_stage_nos", _json_loads(row.get("slice_stage_nos_json"), []))
        structure.setdefault("source", table_name)
        out[plan_no] = structure
    return out


def fill_turn_flows(
    request: dict[str, Any],
    pg_conn,
    db,
    *,
    flow_date: str | None = None,
    prefer_precomputed: bool = True,
) -> dict[str, Any]:
    """用 PG 车道流量为相位方案请求填充 turnFlowTotal / criticalLaneFlow（veh/h）。

    统计口径：
        - 每个方案按其日计划执行时段（fetch_plan_periods）统计；
          库内无时段配置的方案回退为全天 00:00-24:00；
        - turnFlowTotal 为该转向所有车道 5 分钟过车数累加后除以实际观测
          时长换算的小时流量；
        - criticalLaneFlow 取该转向各车道「时段内 5 分钟流量换算 veh/h 后
          80% 分位数」的最大值，作为优化器的关键车道流量输入；
        - 若 phaseDirInfoDTOList 含 signalAtom，则优先经 laneGroupKey 填充细粒度流量；
          无映射或低置信时回退为既有 (dir8No, turnDirNo) 粗桶；
        - 掉头粗桶仍兼容历史逻辑；存在分离掉头车道簇时由 laneGroupKey 单独填充；
        - 渠化以 PG 路网宽表为物理真值（按 link_id 区分主辅路进口），不再使用
          MySQL 路口渠化信息表按方向硬合并的结果。
        - 相位配置与流量侧 8 方向编码偏差（如配置标「南」、渠化标「西南」）
          按相邻方向唯一匹配回退（见 _build_dir_remap）。

    填充结果写回 request（原地修改并返回）；每个方案附加 turnFlowSource
    元数据（流量日期、时段、观测时长、方向回退映射），便于追溯。
    """
    if prefer_precomputed and _apply_precomputed_turn_flows(request, db):
        return request
    if pg_conn is None:
        raise RuntimeError("dws_turn_flow_5min_mm 无可用预计算流量，且未提供 PostgreSQL 连接用于重算")

    from data.pg_reader import fetch_channelization, fetch_turn_flow_stats

    inter_id = request.get("interId") or ""
    periods = fetch_plan_periods(db, inter_id)
    try:
        channelization = fetch_channelization(pg_conn, inter_id)
        lane_groups = build_lane_groups(channelization)
    except Exception:  # noqa: BLE001 - 渠化不可用时保守回退粗桶
        lane_groups = []
    for plan in request.get("phasePlanOfTimeList") or []:
        windows = periods.get(plan.get("planNo")) or [("00:00", "24:00")]
        stats = fetch_turn_flow_stats(pg_conn, inter_id, date=flow_date, windows=windows)
        left_flow_by_dir: dict[int, dict[str, Any]] = {}
        for item in stats["flows"]:
            if item.get("turn") == "left":
                left_flow_by_dir[item["dir8No"]] = item
        flow_index = {
            (item["dir8No"], item["turnDirNo"]): item["flowVph"] for item in stats["flows"]
        }
        critical_index = {
            (item["dir8No"], item["turnDirNo"]): item.get("criticalLaneVph") or 0
            for item in stats["flows"]
        }
        lane_group_flow_index = {
            lane_group_key(item): item
            for item in stats.get("laneGroups") or []
            if lane_group_key(item)
        }
        dir_infos = [
            dir_info
            for stage in plan.get("phaseStageInfoList") or []
            for dir_info in stage.get("phaseDirInfoDTOList") or []
        ]
        plan_dirs = {d.get("dir8No") for d in dir_infos if _to_int(d.get("dir8No")) is not None}
        flow_dirs = {key[0] for key in flow_index}
        dir_remap = _build_dir_remap(plan_dirs, flow_dirs)
        mapping_counts = {"high": 0, "medium": 0, "low": 0, "blocked": 0}
        low_confidence_atoms: list[str] = []
        for dir_info in dir_infos:
            dir8_no = dir_remap.get(dir_info.get("dir8No"), dir_info.get("dir8No"))
            turn_dir_no = _to_int(dir_info.get("turnDirNo"))
            mapping = None
            existing_group_ids = [
                str(group_id)
                for group_id in dir_info.get("laneGroupIds") or []
                if str(group_id)
            ]
            existing_confidence = str((dir_info.get("flowMapping") or {}).get("confidence") or "")
            if existing_group_ids and existing_confidence in {"high", "medium"}:
                group_items = [
                    lane_group_flow_index[group_id]
                    for group_id in existing_group_ids
                    if group_id in lane_group_flow_index
                ]
                mapping_counts[existing_confidence] = mapping_counts.get(existing_confidence, 0) + 1
                if group_items:
                    flow_vph = sum(item.get("flowVph") or 0 for item in group_items)
                    critical = max((item.get("criticalLaneVph") or 0 for item in group_items), default=0)
                    lane_nos = sorted(
                        {
                            lane_no
                            for item in group_items
                            for lane_no in (item.get("laneNos") or [])
                            if _to_int(lane_no) is not None
                        }
                    )
                    dir_info["turnFlowTotal"] = flow_vph
                    dir_info["criticalLaneFlow"] = critical
                    dir_info["laneNos"] = lane_nos or dir_info.get("laneNos") or []
                    dir_info["laneCount"] = max(1, len(dir_info["laneNos"]) or len(dir_info.get("laneNos") or []))
                    dir_info["flowMapping"] = {
                        **(dir_info.get("flowMapping") or {}),
                        "method": "precomputed_lane_phase_mapping",
                        "laneGroupIds": existing_group_ids,
                    }
                    continue
            if dir_info.get("signalAtom"):
                atom_payload = {
                    "signalAtom": dir_info.get("signalAtom"),
                    "sourceKey": dir_info.get("sourceKey") or "",
                    "dir8No": dir8_no,
                    "turnDirNo": turn_dir_no,
                }
                mapping = resolve_atom_lane_mapping(atom_payload, lane_groups).to_dict()
                dir_info["movementKey"] = mapping["movementKey"]
                dir_info["flowMapping"] = mapping
                mapping_counts[mapping["confidence"]] = mapping_counts.get(mapping["confidence"], 0) + 1
                if mapping["confidence"] in {"low", "blocked"}:
                    low_confidence_atoms.append(str(dir_info.get("signalAtom")))
                group_items = [
                    lane_group_flow_index[group_id]
                    for group_id in mapping.get("laneGroupIds") or []
                    if group_id in lane_group_flow_index
                ]
                if mapping["confidence"] in {"high", "medium"} and group_items:
                    flow_vph = sum(item.get("flowVph") or 0 for item in group_items)
                    critical = max((item.get("criticalLaneVph") or 0 for item in group_items), default=0)
                    lane_nos = sorted(
                        {
                            lane_no
                            for item in group_items
                            for lane_no in (item.get("laneNos") or [])
                            if _to_int(lane_no) is not None
                        }
                    )
                    dir_info["turnFlowTotal"] = flow_vph
                    dir_info["criticalLaneFlow"] = critical
                    dir_info["laneGroupIds"] = mapping.get("laneGroupIds") or []
                    dir_info["laneNos"] = lane_nos
                    dir_info["laneCount"] = max(1, len(lane_nos) or len(mapping.get("laneNos") or []))
                    continue
            left_item = left_flow_by_dir.get(dir8_no)
            left_kind = left_item.get("leftTrafficKind") if left_item else None
            flow_vph = 0
            critical = 0
            if turn_dir_no == 0 and left_item and left_kind in {"uturn", "mixed"}:
                flow_vph = left_item.get("flowVph") or 0
                critical = left_item.get("criticalLaneVph") or 0
            elif turn_dir_no == 1:
                if left_item and left_kind == "uturn":
                    flow_vph = 0
                    critical = 0
                else:
                    key = (dir8_no, turn_dir_no)
                    flow_vph = flow_index.get(key, 0)
                    critical = critical_index.get(key, 0)
            else:
                key = (dir8_no, turn_dir_no)
                flow_vph = flow_index.get(key, 0)
                critical = critical_index.get(key, 0)
            dir_info["turnFlowTotal"] = flow_vph
            if critical > 0:
                dir_info["criticalLaneFlow"] = critical
        plan["turnFlowSource"] = {
            "table": f"{os.getenv('PG_FLOW_SCHEMA', 'xianchang')}.{os.getenv('PG_FLOW_TABLE', 'dwd_tfc_lane_roadcross_flow_5mi')}",
            "date": stats["date"],
            "windows": stats["windows"],
            "observedMinutes": stats["observedMinutes"],
            "unit": "veh/h",
            "dirRemap": {str(k): v for k, v in dir_remap.items()},
            "laneGroupSummary": summarize_lane_groups(lane_groups),
            "channelizationSource": "PG渠化宽表",
            "mappingSummary": mapping_counts,
            "lowConfidenceAtoms": low_confidence_atoms,
        }
    return request


def _apply_precomputed_turn_flows(request: dict[str, Any], db) -> bool:
    table_name = "dws_turn_flow_5min_mm"
    if not _table_exists(db, table_name):
        return False
    inter_id = request.get("interId") or ""
    try:
        with db.cursor() as cur:
            cur.execute(
                f"""
                SELECT inter_id, link_id, turn_dir_no, day_of_week, step_index,
                       inter_name, dir8_code, dir4_code, lane_count,
                       turn_flow_total, critical_lane_flow, sample_count
                FROM `{table_name}`
                WHERE is_deleted = 0 AND inter_id = %s
                """,
                (inter_id,),
            )
            rows = cur.fetchall()
    except Exception:
        return False
    if not rows:
        return False

    by_key: dict[tuple[int | None, str, int], list[dict[str, Any]]] = {}
    for row in rows:
        turn_dir_no = _standard_turn_dir_no(row.get("turn_dir_no"))
        if turn_dir_no is None:
            continue
        dir8_no = normalize_dir8_no(row.get("dir8_code"))
        if dir8_no is None:
            continue
        link_id = str(row.get("link_id") or "")
        by_key.setdefault((dir8_no, link_id, turn_dir_no), []).append(row)

    applied = 0
    for plan in request.get("phasePlanOfTimeList") or []:
        for stage in plan.get("phaseStageInfoList") or []:
            for dir_info in stage.get("phaseDirInfoDTOList") or []:
                turn_dir_no = _standard_turn_dir_no(dir_info.get("turnDirNo"))
                if turn_dir_no is None:
                    continue
                dir8_no = _to_int(dir_info.get("dir8No"))
                from_link_id = str(dir_info.get("fromLinkId") or "")
                candidates = by_key.get((dir8_no, from_link_id, turn_dir_no))
                if not candidates:
                    candidates = [
                        row
                        for (key_dir8_no, _link_id, key_turn), group in by_key.items()
                        if key_dir8_no == dir8_no and key_turn == turn_dir_no
                        for row in group
                    ]
                if not candidates:
                    continue
                flow_total = _avg_float(row.get("turn_flow_total") for row in candidates)
                critical = _avg_float(row.get("critical_lane_flow") for row in candidates)
                lane_count = max(
                    1,
                    int(round(_avg_float(row.get("lane_count") for row in candidates) or 1)),
                )
                dir_info["turnFlowTotal"] = round(flow_total, 1)
                dir_info["laneCount"] = lane_count
                if critical > 0:
                    dir_info["criticalLaneFlow"] = round(critical, 1)
                applied += 1
        plan["turnFlowSource"] = {
            "table": table_name,
            "aggregation": "precomputed_5min_mean",
            "unit": "veh/h",
        }
    return applied > 0


def _build_dir_remap(plan_dirs: set[int], flow_dirs: set[int]) -> dict[int, int]:
    """相位配置方向与流量方向不一致时的保守回退映射。

    仅当「配置中有、流量中无」的方向，与「流量中有、配置中无」的方向
    在 8 方向圆上相邻（距离 1）且双向唯一时才建立映射，避免误配。
    """
    missing_plan = sorted(plan_dirs - flow_dirs)
    spare_flow = sorted(flow_dirs - plan_dirs)
    remap: dict[int, int] = {}
    for plan_dir in missing_plan:
        candidates = [
            flow_dir
            for flow_dir in spare_flow
            if min((plan_dir - flow_dir) % 8, (flow_dir - plan_dir) % 8) == 1
        ]
        if len(candidates) != 1:
            continue
        flow_dir = candidates[0]
        # 该流量方向若同时邻接多个缺失的配置方向，也放弃映射
        back_refs = [
            p
            for p in missing_plan
            if min((p - flow_dir) % 8, (flow_dir - p) % 8) == 1
        ]
        if len(back_refs) == 1:
            remap[plan_dir] = flow_dir
    return remap


def fill_stage_green_bounds(
    request: dict[str, Any],
    db,
    *,
    motor_min_green_s: int = 14,
    prefer_precomputed: bool = True,
) -> dict[str, Any]:
    """按交通流推导各方案/各时段的阶段最小绿与最大绿，写回 request（原地修改并返回）。

    计算规则见 preprocessing.timing.stage_min_green 模块：
        - 机动车流最小绿默认 14s；
        - 行人过街流最小绿 = (方位进口车道数 + 出口车道数) × 3.25m ÷ 1.2m/s；
        - 仅单阶段放行的流取最大值，跨阶段流按"加和 ≥ 流最小绿"分摊；
        - 历史实际放行（方案 green_sec 与时段执行历史 green_exec_sec）更短时取更小值；
        - 无对应交通流的阶段最小绿/最大绿沿用历史方案数值。

    写回内容：
        - 各阶段 min_green_s / max_green_s（供单路口优化器直接消费）与 greenBounds 明细；
        - 各方案 timePeriods（日计划执行时段）与 greenBounds.periods
          （分时段最小绿/最大绿，时段内有执行历史时按该时段实际绿灯修正）。
    """
    if prefer_precomputed and _apply_precomputed_stage_green_bounds(request, db, motor_min_green_s):
        return request

    from preprocessing.timing.stage_min_green import (
        apply_history_green_stability_floor,
        compute_stage_green_bounds,
    )

    inter_id = request.get("interId") or ""
    crossing_lanes = _crossing_lanes_by_dir(db, inter_id)
    periods = fetch_plan_periods(db, inter_id)
    exec_history = _fetch_exec_green_history(db, inter_id)

    for plan in request.get("phasePlanOfTimeList") or []:
        plan_no = _to_int(plan.get("planNo"))
        stages_payload = plan.get("phaseStageInfoList") or []
        if not stages_payload:
            continue

        stage_inputs = []
        key_by_stage_no: dict[int, str] = {}
        for stage in stages_payload:
            stage_key = str(stage.get("phaseStageId"))
            stage_no = _to_int(stage.get("stageNo"))
            if stage_no is not None:
                key_by_stage_no[stage_no] = stage_key
            timing = stage.get("currentTiming") or {}
            stage_inputs.append(
                {
                    "stageKey": stage_key,
                    "motorFlows": [
                        (d.get("dir8No"), d.get("turnDirNo"))
                        for d in stage.get("phaseDirInfoDTOList") or []
                        if _to_int(d.get("dir8No")) is not None
                        and _to_int(d.get("turnDirNo")) is not None
                    ],
                    "pedDirs": stage.get("pedDirList") or [],
                    "historyGreenS": timing.get("greenSec"),
                    "historyMinGreenS": stage.get("min_green_s"),
                    "historyMaxGreenS": stage.get("max_green_s"),
                }
            )

        plan_exec = [entry for entry in exec_history if entry[0] == plan_no]
        plan_overrides = _exec_overrides(plan_exec, key_by_stage_no)
        result = compute_stage_green_bounds(
            stage_inputs,
            crossing_lanes,
            motor_min_green_s=motor_min_green_s,
            actual_green_overrides=plan_overrides,
        )
        for stage in stages_payload:
            bounds = result["stages"].get(str(stage.get("phaseStageId")))
            if not bounds:
                continue
            history_green = _stage_history_green_s(stage)
            if bounds["minGreenS"] is not None:
                effective_min = apply_history_green_stability_floor(
                    int(bounds["minGreenS"]),
                    history_green,
                )
                stage["min_green_s"] = effective_min
                bounds = {**bounds, "minGreenS": effective_min}
            if bounds["maxGreenS"] is not None:
                stage["max_green_s"] = bounds["maxGreenS"]
            stage["greenBounds"] = bounds

        # 分时段：时段内有执行历史时按该时段实际绿灯修正（规则 4 / 6）
        windows = periods.get(plan_no) or []
        period_bounds = []
        for start, end in windows:
            window_exec = [entry for entry in plan_exec if _hhmm_in_window(entry[1], start, end)]
            window_overrides = _exec_overrides(window_exec, key_by_stage_no) or plan_overrides
            window_result = compute_stage_green_bounds(
                stage_inputs,
                crossing_lanes,
                motor_min_green_s=motor_min_green_s,
                actual_green_overrides=window_overrides,
            )
            window_stages: dict[str, dict[str, Any]] = {}
            for stage in stages_payload:
                stage_key = str(stage.get("phaseStageId"))
                bounds = window_result["stages"].get(stage_key)
                if not bounds:
                    continue
                override_green = (
                    _to_positive_float(window_overrides.get(stage_key))
                    if stage_key in window_overrides
                    else None
                )
                history_green = override_green if override_green is not None else _stage_history_green_s(stage)
                if bounds.get("minGreenS") is not None:
                    bounds = {
                        **bounds,
                        "minGreenS": apply_history_green_stability_floor(
                            int(bounds["minGreenS"]),
                            history_green,
                        ),
                    }
                window_stages[stage_key] = bounds
            period_bounds.append(
                {
                    "startTime": start,
                    "endTime": end,
                    "stages": window_stages,
                }
            )

        plan["timePeriods"] = [{"startTime": s, "endTime": e} for s, e in windows]
        plan["greenBounds"] = {
            "flows": result["flows"],
            "periods": period_bounds,
            "params": {
                "motorMinGreenS": motor_min_green_s,
                "laneWidthM": 3.25,
                "pedWalkSpeedMps": 1.2,
                "crossingLanesByDir": crossing_lanes,
            },
        }
    return request


def _apply_precomputed_stage_green_bounds(
    request: dict[str, Any],
    db,
    motor_min_green_s: int,
) -> bool:
    table_name = "dws_stage_green_bounds_5min_mm"
    if not _table_exists(db, table_name):
        return False
    inter_id = request.get("interId") or ""
    try:
        with db.cursor() as cur:
            cur.execute(
                f"""
                SELECT plan_no, stage_no, stage_seq_no, day_of_week, step_index,
                       cycle_len_sec, history_green_s, history_min_green_s,
                       history_max_green_s, min_green_s, max_green_s,
                       pinned_to_history, has_motor_flow, has_pedestrian_flow,
                       CAST(green_bounds_json AS CHAR) AS green_bounds_json
                FROM `{table_name}`
                WHERE is_deleted = 0 AND inter_id = %s
                ORDER BY plan_no, stage_seq_no, day_of_week, step_index
                """,
                (inter_id,),
            )
            rows = cur.fetchall()
    except Exception:
        return False
    if not rows:
        return False

    by_plan_stage: dict[tuple[int, int], list[dict[str, Any]]] = {}
    by_plan: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        plan_no = _to_int(row.get("plan_no"))
        stage_no = _to_int(row.get("stage_no"))
        if plan_no is None or stage_no is None:
            continue
        by_plan_stage.setdefault((plan_no, stage_no), []).append(row)
        by_plan.setdefault(plan_no, []).append(row)

    applied = 0
    for plan in request.get("phasePlanOfTimeList") or []:
        plan_no = _to_int(plan.get("planNo"))
        if plan_no is None:
            continue
        plan_rows = by_plan.get(plan_no) or []
        if not plan_rows:
            continue
        for stage in plan.get("phaseStageInfoList") or []:
            stage_no = _to_int(stage.get("stageNo"))
            if stage_no is None:
                continue
            candidates = by_plan_stage.get((plan_no, stage_no)) or []
            if not candidates:
                continue
            selected = candidates[0]
            bounds = {
                "minGreenS": _number_or_none(selected.get("min_green_s")),
                "maxGreenS": _number_or_none(selected.get("max_green_s")),
                "pinnedToHistory": bool(_to_int(selected.get("pinned_to_history"))),
                "notes": ["来自预计算表 dws_stage_green_bounds_5min_mm"],
                "source": table_name,
            }
            if bounds["minGreenS"] is not None:
                stage["min_green_s"] = bounds["minGreenS"]
            if bounds["maxGreenS"] is not None:
                stage["max_green_s"] = bounds["maxGreenS"]
            stage["greenBounds"] = bounds
            applied += 1
        plan["timePeriods"] = _periods_from_precomputed_rows(plan_rows)
        plan["greenBounds"] = {
            "source": table_name,
            "periods": _period_bounds_from_precomputed_rows(plan_rows),
            "params": {
                "motorMinGreenS": motor_min_green_s,
                "precomputed": True,
            },
        }
    return applied > 0


def _periods_from_precomputed_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[int, int]] = set()
    periods: list[dict[str, Any]] = []
    for row in rows:
        day_of_week = _to_int(row.get("day_of_week"))
        step_index = _to_int(row.get("step_index"))
        if day_of_week is None or step_index is None or (day_of_week, step_index) in seen:
            continue
        seen.add((day_of_week, step_index))
        periods.append(
            {
                "dayOfWeek": day_of_week,
                "stepIndex": step_index,
                "startTime": _step_index_to_hhmm(step_index),
                "endTime": _step_index_to_hhmm(min(step_index + 1, 288)),
            }
        )
    return periods


def _period_bounds_from_precomputed_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        day_of_week = _to_int(row.get("day_of_week"))
        step_index = _to_int(row.get("step_index"))
        stage_no = _to_int(row.get("stage_no"))
        if day_of_week is None or step_index is None or stage_no is None:
            continue
        key = (day_of_week, step_index)
        item = grouped.setdefault(
            key,
            {
                "dayOfWeek": day_of_week,
                "stepIndex": step_index,
                "startTime": _step_index_to_hhmm(step_index),
                "endTime": _step_index_to_hhmm(min(step_index + 1, 288)),
                "stages": {},
            },
        )
        stage_key = f"S{stage_no}"
        item["stages"][stage_key] = {
            "minGreenS": _number_or_none(row.get("min_green_s")),
            "maxGreenS": _number_or_none(row.get("max_green_s")),
            "pinnedToHistory": bool(_to_int(row.get("pinned_to_history"))),
            "source": "dws_stage_green_bounds_5min_mm",
        }
    return [grouped[key] for key in sorted(grouped)]


def _step_index_to_hhmm(step_index: int) -> str:
    minutes = min(max(step_index, 0), 288) * 5
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _crossing_lanes_by_dir(db, inter_id: str) -> dict[int, int]:
    """各方位行人过街需跨越的车道数 = 进口车道数 + 出口车道数（0 基 dir8No）。

    渠化口径与单路口优化页面一致：仅读 PG 渠化宽表 + dim_link_info.lane_num。
    """
    del db  # 保留参数以兼容 fill_stage_green_bounds 调用签名
    try:
        pg_conn = connect_pg()
    except Exception:
        return {}
    try:
        channel = fetch_channelization(pg_conn, inter_id)
        return _crossing_lanes_from_channel(channel)
    except Exception:
        return {}
    finally:
        pg_conn.close()


def _crossing_lanes_from_channel(channel: dict[str, Any]) -> dict[int, int]:
    """从 PG 渠化结构提取行人过街跨越车道数（0 基 dir8No）。"""
    entry_by_dir: dict[int, int] = {}
    exit_by_dir: dict[int, int] = {}
    for approach in channel.get("approaches") or []:
        dir8_no = normalize_dir8_no(approach.get("dir8Code"))
        if dir8_no is None:
            continue
        lanes = _to_int(approach.get("laneTotal")) or 0
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


def _fetch_exec_green_history(
    db,
    inter_id: str,
) -> list[tuple[int | None, str, dict[int, int]]]:
    """时段方案执行历史 → [(plan_no, 时段开始 "HH:MM", {stage_no: 实际绿灯秒}), ...]。

    表不存在或无数据时返回空列表（最小绿计算退化为仅用方案配置 green_sec）。
    """
    try:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT plan_no, period_start_time,
                       CAST(stage_exec_json AS CHAR) AS stage_exec_json
                FROM dwd_ctl_inter_period_plan_exec_his
                WHERE is_deleted = 0 AND inter_id = %s
                """,
                (inter_id,),
            )
            rows = cur.fetchall()
    except Exception:
        return []

    out: list[tuple[int | None, str, dict[int, int]]] = []
    for row in rows:
        start = row.get("period_start_time")
        hhmm = start.strftime("%H:%M") if isinstance(start, _dt.datetime) else _time_to_hhmm(start)
        if hhmm is None:
            continue
        try:
            stage_exec = json.loads(row.get("stage_exec_json") or "[]")
        except json.JSONDecodeError:
            continue
        greens: dict[int, int] = {}
        for item in stage_exec if isinstance(stage_exec, list) else []:
            if not isinstance(item, dict):
                continue
            stage_no = _to_int(item.get("stage_no"))
            green = _to_int(item.get("green_exec_sec"))
            if stage_no is None or green is None or green <= 0:
                continue
            greens[stage_no] = min(greens.get(stage_no, green), green)
        if greens:
            out.append((_to_int(row.get("plan_no")), hhmm, greens))
    return out


def _exec_overrides(
    entries: list[tuple[int | None, str, dict[int, int]]],
    key_by_stage_no: dict[int, str],
) -> dict[str, int]:
    """多条执行历史按阶段取最小实际绿灯，映射为 {stageKey: 秒}。"""
    merged: dict[int, int] = {}
    for _plan_no, _hhmm, greens in entries:
        for stage_no, green in greens.items():
            merged[stage_no] = min(merged.get(stage_no, green), green)
    return {
        key_by_stage_no[stage_no]: green
        for stage_no, green in merged.items()
        if stage_no in key_by_stage_no
    }


def _hhmm_in_window(hhmm: str, start: str, end: str) -> bool:
    """时段命中判断；start > end 视为跨午夜窗口。"""
    if start <= end:
        return start <= hhmm < end
    return hhmm >= start or hhmm < end


def export_intersection_data(
    output_dir: str | Path,
    *,
    inter_ids: list[str] | None = None,
    plan_no: int | None = None,
    with_flows: bool = False,
    flow_date: str | None = None,
    prefer_precomputed: bool = True,
    recompute_green_bounds: bool = False,
    recompute_flows: bool = False,
) -> dict[str, int]:
    """从 MySQL 导出路口列表与相位相序方案 JSON 文件。

    产物：
        - <output_dir>/intersections.json            路口列表
        - <output_dir>/phase_plans/<inter_id>.json   单路口优化器输入骨架

    with_flows=True 时按方案执行时段从 PG 车道流量表统计小时流量，
    填充 phase_plans 中各转向的 turnFlowTotal（flow_date 缺省取库内最新一天）。
    """
    output = Path(output_dir)
    db = connect_mysql()
    pg_conn = None
    if with_flows:
        from data.pg_reader import connect_pg

        pg_conn = connect_pg()
    try:
        intersections = fetch_intersection_list(db)
        exported_at = _dt.datetime.now().isoformat(timespec="seconds")
        write_json(
            output / "intersections.json",
            {
                "exported_at": exported_at,
                "source": {
                    "database": os.getenv("MYSQL_DATABASE", "signalctl"),
                    "tables": [
                        "dwd_ctl_inter_plan_cfg",
                        "dwd_ctl_inter_stage_cfg",
                        "dwd_ctl_inter_day_plan_cfg",
                    ],
                },
                "intersection_count": len(intersections),
                "intersections": intersections,
            },
        )

        targets = inter_ids or [item["interId"] for item in intersections]
        known = {item["interId"] for item in intersections}
        plan_file_count = 0
        flow_filled_count = 0
        for inter_id in targets:
            if inter_ids and inter_id not in known:
                print(f"跳过：库内无路口 {inter_id} 的配时方案")
                continue
            request = fetch_phase_plan_request(db, inter_id, plan_no=plan_no)
            if not request["phasePlanOfTimeList"]:
                continue
            try:
                fill_stage_green_bounds(
                    request,
                    db,
                    prefer_precomputed=prefer_precomputed and not recompute_green_bounds,
                )
            except Exception as exc:
                print(f"警告：路口 {inter_id} 阶段最小绿计算失败: {exc}")
            if pg_conn is not None:
                try:
                    fill_turn_flows(
                        request,
                        pg_conn,
                        db,
                        flow_date=flow_date,
                        prefer_precomputed=prefer_precomputed and not recompute_flows,
                    )
                    flow_filled_count += 1
                except Exception as exc:
                    print(f"警告：路口 {inter_id} 流量填充失败: {exc}")
            write_json(output / "phase_plans" / f"{inter_id}.json", request)
            plan_file_count += 1
    finally:
        db.close()
        if pg_conn is not None:
            pg_conn.close()

    counts = {"路口数": len(intersections), "相位方案文件数": plan_file_count}
    if with_flows:
        counts["流量填充路口数"] = flow_filled_count
    return counts


def _stage_payload(row: dict[str, Any]) -> dict[str, Any]:
    stage_no = row["stage_no"]
    return {
        "phaseStageId": f"S{stage_no}",
        "phaseStageName": row.get("stage_name") or f"阶段{stage_no}",
        "stageSeqNo": row["stage_seq_no"],
        "stageNo": stage_no,
        "currentTiming": {
            "greenSec": row.get("green_sec") or 0,
            "yellowSec": row.get("yellow_sec") or 0,
            "allRedSec": row.get("all_red_sec") or 0,
            "stageTotalSec": row.get("stage_total_sec") or 0,
        },
        "min_green_s": row.get("min_green_sec"),
        "max_green_s": row.get("max_green_sec"),
        "yellow_s": row.get("yellow_sec"),
        "all_red_s": row.get("all_red_sec"),
        "phaseDirInfoDTOList": _flow_combo_to_dir_info(row.get("flow_combo_json")),
        "pedDirList": _flow_combo_to_ped_dirs(row.get("flow_combo_json")),
    }


def _fetch_lane_phase_dir_infos(
    db,
    inter_id: str,
    *,
    plan_no: int | None = None,
) -> dict[int, dict[int, list[dict[str, Any]]]]:
    """统一映射表 → {plan_no: {stage_no: phaseDirInfoDTOList}}。"""
    table_name = "dwd_ctl_inter_plan_lane_phase_mapping"
    if not _table_exists(db, table_name):
        return {}
    params: list[Any] = [inter_id]
    plan_filter = ""
    if plan_no is not None:
        plan_filter = " AND plan_no = %s"
        params.append(plan_no)
    try:
        with db.cursor() as cur:
            cur.execute(
                f"""
                SELECT plan_no, link_id, lane_group_id,
                       CAST(lane_nos_json AS CHAR) AS lane_nos_json,
                       signal_atom, source_key, source_type, release_kind,
                       dir8_no, turn_dir_no, movement_key,
                       CAST(stage_nos_json AS CHAR) AS stage_nos_json,
                       CAST(parent_source_keys_json AS CHAR) AS parent_source_keys_json,
                       confidence, score, is_controlled
                FROM `{table_name}`
                WHERE is_deleted = 0
                  AND inter_id = %s
                  AND is_controlled = 1
                  AND confidence IN ('high', 'medium')
                  {plan_filter}
                ORDER BY plan_no, source_key, signal_atom, lane_group_id
                """,
                params,
            )
            rows = list(cur.fetchall())
    except Exception:
        return {}

    out: dict[int, dict[int, list[dict[str, Any]]]] = {}
    seen: set[tuple[int, int, str, str, int | None, int | None, str]] = set()
    for row in rows:
        current_plan_no = _to_int(row.get("plan_no"))
        dir8_no = _to_int(row.get("dir8_no"))
        turn_dir_no = _standard_turn_dir_no(row.get("turn_dir_no"))
        movement_key = str(row.get("movement_key") or "")
        signal_atom = str(row.get("signal_atom") or "")
        source_key = str(row.get("source_key") or "")
        if current_plan_no is None or dir8_no not in DIR8_LABELS or turn_dir_no not in TURN_DIR_LABELS:
            continue
        stage_nos = [
            int(value)
            for value in _parse_json_list(row.get("stage_nos_json"))
            if _to_int(value) is not None
        ]
        if not stage_nos:
            continue
        lane_nos = [
            int(value)
            for value in _parse_json_list(row.get("lane_nos_json"))
            if _to_int(value) is not None
        ]
        lane_group_id = str(row.get("lane_group_id") or "")
        parent_source_keys = [
            str(value)
            for value in _parse_json_list(row.get("parent_source_keys_json"))
            if str(value)
        ]
        for stage_no in stage_nos:
            dedupe_key = (current_plan_no, stage_no, movement_key, source_key, dir8_no, turn_dir_no, lane_group_id)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            item = {
                "dir8No": dir8_no,
                "turnDirNo": turn_dir_no,
                "dirName": DIR8_LABELS[dir8_no],
                "turnName": TURN_DIR_LABELS[turn_dir_no],
                "turnFlowTotal": 0,
                "laneCount": max(1, len(lane_nos)),
                "fromLinkId": row.get("link_id") or "",
                "signalAtom": signal_atom,
                "sourceKey": source_key,
                "sourceType": row.get("source_type") or "",
                "releaseKind": row.get("release_kind") or "",
                "movementKey": movement_key or movement_key_for_atom(signal_atom, source_key),
                "laneGroupIds": [lane_group_id] if lane_group_id else [],
                "laneNos": lane_nos,
                "flowMapping": {
                    "source": table_name,
                    "confidence": row.get("confidence") or "",
                    "score": _to_int(row.get("score")) or 0,
                    "releaseKind": row.get("release_kind") or "",
                    "parentSourceKeys": parent_source_keys,
                    "isControlled": bool(_to_int(row.get("is_controlled")) or 0),
                },
            }
            out.setdefault(current_plan_no, {}).setdefault(stage_no, []).append(item)
    return out


def _flow_combo_to_dir_info(flow_combo_json: Any) -> list[dict[str, Any]]:
    """flow_combo_json → phaseDirInfoDTOList，转换方向/转向编码并按 signalAtom 去重。"""
    try:
        combo = json.loads(flow_combo_json) if isinstance(flow_combo_json, str) else flow_combo_json
    except json.JSONDecodeError:
        return []
    if not isinstance(combo, list):
        return []

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()
    for item in combo:
        if not isinstance(item, dict):
            continue
        turn_dir_no = FLOW_TYPE_TO_TURN_DIR.get(_to_int(item.get("flow_type_no")))
        dir8_no = dir8_no_from_flow_combo_item(item)
        if turn_dir_no is None or dir8_no is None:
            continue
        signal_atom = str(item.get("signal_atom") or item.get("signalAtom") or "")
        source_key = str(item.get("source_key") or item.get("sourceKey") or "")
        key = (signal_atom, source_key, dir8_no, turn_dir_no)
        if dir8_no not in DIR8_LABELS or key in seen:
            continue
        seen.add(key)
        payload = {
            "dir8No": dir8_no,
            "turnDirNo": turn_dir_no,
            "dirName": DIR8_LABELS[dir8_no],
            "turnName": TURN_DIR_LABELS[turn_dir_no],
            "turnFlowTotal": 0,
            "laneCount": 1,
            "fromLinkId": item.get("from_link_id") or "",
        }
        if signal_atom:
            payload.update(
                {
                    "signalAtom": signal_atom,
                    "vendorTag": item.get("vendor_tag") or item.get("vendorTag") or "",
                    "sourceKey": source_key,
                    "sourceType": item.get("source_type") or item.get("sourceType") or "",
                    "turnSet": item.get("turn_set") or item.get("turnSet") or [],
                    "movementKey": item.get("movement_key")
                    or item.get("movementKey")
                    or movement_key_for_atom(signal_atom, source_key),
                }
            )
        out.append(payload)
    return out


def _flow_combo_to_ped_dirs(flow_combo_json: Any) -> list[int]:
    """flow_combo_json → 行人过街流方位列表（flow_type_no=5，0 基 dir8No）。"""
    try:
        combo = json.loads(flow_combo_json) if isinstance(flow_combo_json, str) else flow_combo_json
    except json.JSONDecodeError:
        return []
    if not isinstance(combo, list):
        return []

    out: list[int] = []
    for item in combo:
        if not isinstance(item, dict) or _to_int(item.get("flow_type_no")) != 5:
            continue
        dir8_no = dir8_no_from_flow_combo_item(item)
        if dir8_no is None:
            continue
        if dir8_no in DIR8_LABELS and dir8_no not in out:
            out.append(dir8_no)
    return out


def _match_base_info(
    base_by_cross_no: dict[int, dict[str, Any]],
    cross_id: str,
) -> dict[str, Any] | None:
    try:
        return base_by_cross_no.get(int(cross_id))
    except (TypeError, ValueError):
        return None


def _base_payload(base: dict[str, Any] | None) -> dict[str, Any] | None:
    if not base:
        return None
    return {
        "baseId": base.get("id"),
        "name": base.get("name"),
        "controlVendor": base.get("control_vendor"),
        "controlCrossroadId": base.get("control_crossroad_id"),
        "platformId": base.get("platform_id"),
        "lon": base.get("lon"),
        "lat": base.get("lat"),
        "adcode": base.get("adcode"),
    }


def _extract_name(remark: str | None) -> str | None:
    if not remark:
        return None
    match = _NAME_PATTERN.search(remark)
    return match.group(1).strip() if match else None


def _json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _to_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _standard_turn_dir_no(value: Any) -> int | None:
    turn_dir_no = _to_int(value)
    if turn_dir_no in {0, 1}:
        return 1
    if turn_dir_no in {2, 3}:
        return turn_dir_no
    return None


def _avg_float(values: Any) -> float:
    numbers: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        numbers.append(number)
    return sum(numbers) / len(numbers) if numbers else 0.0


def _number_or_none(value: Any) -> int | float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _stage_history_green_s(stage: dict[str, Any]) -> float | None:
    timing = stage.get("currentTiming") if isinstance(stage.get("currentTiming"), dict) else {}
    return _to_positive_float(timing.get("greenSec"))


def _time_to_hhmm(value: Any) -> str | None:
    """MySQL TIME（pymysql 返回 timedelta）→ "HH:MM" 字符串。"""
    if isinstance(value, _dt.timedelta):
        total_minutes = int(value.total_seconds()) // 60
        return f"{min(total_minutes // 60, 24):02d}:{total_minutes % 60:02d}"
    if isinstance(value, _dt.time):
        return value.strftime("%H:%M")
    if isinstance(value, str) and re.match(r"^\d{1,2}:\d{2}", value):
        hour, minute = value.split(":")[:2]
        return f"{int(hour):02d}:{minute[:2]}"
    return None


def _parse_json_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _phase_no_from_source_key(source_key: str) -> int | None:
    match = re.match(r"^(?:P|OP)(\d+)$", str(source_key or "").strip(), re.IGNORECASE)
    if not match:
        return None
    return _to_int(match.group(1))


def fetch_atom_lane_mapping(
    db,
    inter_id: str,
    plan_no: int,
) -> dict[str, Any]:
    """读取 dwd_ctl_inter_signal_atom_lane_mapping，并关联阶段-相位关系。"""
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT signal_atom, source_key, source_type, vendor_tag,
                   dir8_no, turn_dir_no, link_id, lane_group_id,
                   lane_nos_json, cluster_kind, capabilities_json,
                   movement_key, confidence, score, stage_no
            FROM dwd_ctl_inter_signal_atom_lane_mapping
            WHERE is_deleted = 0
              AND inter_id = %s
              AND plan_no = %s
            ORDER BY source_key, signal_atom, source_key
            """,
            (inter_id, plan_no),
        )
        rows = list(cur.fetchall())

        cur.execute(
            """
            SELECT source_key, source_type, source_no, stage_no, stage_seq_no,
                   ring_no, is_active_green
            FROM dwd_ctl_inter_plan_stage_phase_rltn
            WHERE is_deleted = 0
              AND inter_id = %s
              AND plan_no = %s
            ORDER BY stage_seq_no, source_type, source_no
            """,
            (inter_id, plan_no),
        )
        stage_phase_rows = list(cur.fetchall())

    stage_by_source: dict[str, list[dict[str, Any]]] = {}
    for row in stage_phase_rows:
        key = str(row.get("source_key") or "")
        if not key:
            continue
        stage_by_source.setdefault(key, []).append(
            {
                "stageNo": _to_int(row.get("stage_no")),
                "stageSeqNo": _to_int(row.get("stage_seq_no")),
                "sourceNo": _to_int(row.get("source_no")),
                "sourceType": row.get("source_type") or "",
                "ringNo": _to_int(row.get("ring_no")),
                "isActiveGreen": bool(_to_int(row.get("is_active_green")) or 0),
            }
        )

    mappings: list[dict[str, Any]] = []
    lane_cluster_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_key = str(row.get("source_key") or "")
        lane_nos = [
            int(x)
            for x in _parse_json_list(row.get("lane_nos_json"))
            if _to_int(x) is not None
        ]
        capabilities = [str(x) for x in _parse_json_list(row.get("capabilities_json"))]
        stage_refs = stage_by_source.get(source_key) or []
        stage_nos = sorted({s["stageNo"] for s in stage_refs if s.get("stageNo") is not None})
        item = {
            "signalAtom": row.get("signal_atom") or "",
            "sourceKey": source_key,
            "sourceType": row.get("source_type") or "",
            "phaseNo": _phase_no_from_source_key(source_key),
            "vendorTag": row.get("vendor_tag") or "",
            "dir8No": _to_int(row.get("dir8_no")),
            "turnDirNo": _to_int(row.get("turn_dir_no")),
            "linkId": row.get("link_id") or "",
            "laneGroupId": row.get("lane_group_id") or "",
            "laneNos": lane_nos,
            "clusterKind": row.get("cluster_kind") or "",
            "capabilities": capabilities,
            "movementKey": row.get("movement_key") or "",
            "confidence": row.get("confidence") or "",
            "score": _to_int(row.get("score")) or 0,
            "stageNo": _to_int(row.get("stage_no")),
            "stageNos": stage_nos,
            "stageRefs": stage_refs,
        }
        mappings.append(item)

        cluster_key = item["laneGroupId"] or (
            f"{item['linkId']}|{item['dir8No']}|{','.join(str(n) for n in lane_nos)}"
        )
        if not cluster_key or cluster_key == "||":
            continue
        cluster = lane_cluster_map.setdefault(
            cluster_key,
            {
                "laneGroupId": item["laneGroupId"],
                "linkId": item["linkId"],
                "dir8No": item["dir8No"],
                "laneNos": lane_nos,
                "clusterKind": item["clusterKind"],
                "capabilities": capabilities,
                "phases": [],
                "signalAtoms": [],
            },
        )
        phase_entry = {
            "sourceKey": source_key,
            "phaseNo": item["phaseNo"],
            "signalAtom": item["signalAtom"],
            "stageNos": stage_nos,
            "confidence": item["confidence"],
        }
        if phase_entry not in cluster["phases"]:
            cluster["phases"].append(phase_entry)
        if item["signalAtom"] and item["signalAtom"] not in cluster["signalAtoms"]:
            cluster["signalAtoms"].append(item["signalAtom"])

    return {
        "interId": inter_id,
        "planNo": plan_no,
        "mappingCount": len(mappings),
        "laneClusterCount": len(lane_cluster_map),
        "mappings": mappings,
        "laneClusters": list(lane_cluster_map.values()),
        "sourceTable": "dwd_ctl_inter_signal_atom_lane_mapping",
    }


def fetch_lane_phase_mapping(
    db,
    inter_id: str,
    plan_no: int,
) -> dict[str, Any]:
    """读取 plan 级车道簇-相位-阶段统一映射表。"""
    table_name = "dwd_ctl_inter_plan_lane_phase_mapping"
    if not _table_exists(db, table_name):
        return {
            "interId": inter_id,
            "planNo": plan_no,
            "mappingCount": 0,
            "laneClusterCount": 0,
            "mappings": [],
            "laneClusters": [],
            "sourceTable": table_name,
            "tableExists": False,
            "schemaVersion": "lane_phase_mapping_v1",
        }

    with db.cursor() as cur:
        cur.execute(
            f"""
            SELECT signal_atom, source_key, source_type, release_kind,
                   dir8_no, turn_dir_no, link_id, lane_group_id,
                   CAST(lane_nos_json AS CHAR) AS lane_nos_json,
                   cluster_kind,
                   CAST(capabilities_json AS CHAR) AS capabilities_json,
                   movement_key,
                   CAST(stage_nos_json AS CHAR) AS stage_nos_json,
                   CAST(parent_source_keys_json AS CHAR) AS parent_source_keys_json,
                   is_active_green,
                   CAST(included_phase_nos_json AS CHAR) AS included_phase_nos_json,
                   CAST(modifier_phase_nos_json AS CHAR) AS modifier_phase_nos_json,
                   confidence, score, is_controlled
            FROM `{table_name}`
            WHERE is_deleted = 0
              AND inter_id = %s
              AND plan_no = %s
            ORDER BY lane_group_id, source_key, signal_atom
            """,
            (inter_id, plan_no),
        )
        rows = list(cur.fetchall())

    mappings: list[dict[str, Any]] = []
    lane_cluster_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_key = str(row.get("source_key") or "")
        lane_nos = [
            int(x)
            for x in _parse_json_list(row.get("lane_nos_json"))
            if _to_int(x) is not None
        ]
        capabilities = [str(x) for x in _parse_json_list(row.get("capabilities_json"))]
        stage_nos = [
            int(x)
            for x in _parse_json_list(row.get("stage_nos_json"))
            if _to_int(x) is not None
        ]
        parent_source_keys = [
            str(x) for x in _parse_json_list(row.get("parent_source_keys_json")) if str(x)
        ]
        item = {
            "signalAtom": row.get("signal_atom") or "",
            "sourceKey": source_key,
            "sourceType": row.get("source_type") or "",
            "releaseKind": row.get("release_kind") or "",
            "phaseNo": _phase_no_from_source_key(source_key),
            "dir8No": _to_int(row.get("dir8_no")),
            "turnDirNo": _to_int(row.get("turn_dir_no")),
            "linkId": row.get("link_id") or "",
            "laneGroupId": row.get("lane_group_id") or "",
            "laneNos": lane_nos,
            "clusterKind": row.get("cluster_kind") or "",
            "capabilities": capabilities,
            "movementKey": row.get("movement_key") or "",
            "stageNos": stage_nos,
            "parentSourceKeys": parent_source_keys,
            "isActiveGreen": bool(_to_int(row.get("is_active_green")) or 0),
            "includedPhaseNos": _parse_json_list(row.get("included_phase_nos_json")),
            "modifierPhaseNos": _parse_json_list(row.get("modifier_phase_nos_json")),
            "confidence": row.get("confidence") or "",
            "score": _to_int(row.get("score")) or 0,
            "isControlled": bool(_to_int(row.get("is_controlled")) or 0),
        }
        mappings.append(item)

        cluster_key = item["laneGroupId"] or (
            f"{item['linkId']}|{item['dir8No']}|{','.join(str(n) for n in lane_nos)}"
        )
        if not cluster_key or cluster_key == "||":
            continue
        cluster = lane_cluster_map.setdefault(
            cluster_key,
            {
                "laneGroupId": item["laneGroupId"],
                "linkId": item["linkId"],
                "dir8No": item["dir8No"],
                "laneNos": lane_nos,
                "clusterKind": item["clusterKind"],
                "capabilities": capabilities,
                "phases": [],
                "signalAtoms": [],
            },
        )
        phase_entry = {
            "sourceKey": source_key,
            "phaseNo": item["phaseNo"],
            "signalAtom": item["signalAtom"],
            "stageNos": stage_nos,
            "releaseKind": item["releaseKind"],
            "parentSourceKeys": parent_source_keys,
            "confidence": item["confidence"],
            "isControlled": item["isControlled"],
        }
        if phase_entry not in cluster["phases"]:
            cluster["phases"].append(phase_entry)
        if item["signalAtom"] and item["signalAtom"] not in cluster["signalAtoms"]:
            cluster["signalAtoms"].append(item["signalAtom"])

    return {
        "interId": inter_id,
        "planNo": plan_no,
        "mappingCount": len(mappings),
        "laneClusterCount": len(lane_cluster_map),
        "mappings": mappings,
        "laneClusters": list(lane_cluster_map.values()),
        "sourceTable": table_name,
        "tableExists": True,
        "schemaVersion": "lane_phase_mapping_v1",
    }
