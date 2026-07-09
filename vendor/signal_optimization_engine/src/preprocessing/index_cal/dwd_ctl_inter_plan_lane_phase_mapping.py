#!/usr/bin/env python3
"""生成 plan 级车道簇-相位-阶段统一映射表。"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Any

from preprocessing.timing.dir8_encoding import dir8_no_from_flow_combo_item
from preprocessing.timing.atom_lane_mapping import movement_key_for_atom
from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_TARGET = "dwd_ctl_inter_plan_lane_phase_mapping"
TABLE_ATOM_LANE_MAPPING = "dwd_ctl_inter_signal_atom_lane_mapping"
TABLE_PLAN_STAGE_PHASE_RLTN = "dwd_ctl_inter_plan_stage_phase_rltn"
TABLE_STAGE_CFG = "dwd_ctl_inter_stage_cfg"
TABLE_PLAN_CFG = "dwd_ctl_inter_plan_cfg"
SCHEMA_VERSION = "lane_phase_mapping_v1"

TARGET_COLUMNS = [
    "inter_id",
    "cross_id",
    "plan_no",
    "link_id",
    "lane_group_id",
    "lane_nos_json",
    "cluster_kind",
    "capabilities_json",
    "signal_atom",
    "source_key",
    "source_type",
    "release_kind",
    "dir8_no",
    "turn_dir_no",
    "movement_key",
    "stage_nos_json",
    "parent_source_keys_json",
    "is_active_green",
    "included_phase_nos_json",
    "modifier_phase_nos_json",
    "confidence",
    "score",
    "evidence_json",
    "is_controlled",
    "schema_version",
    "is_deleted",
]


def ensure_target_table(conn: Any, table_name: str = TABLE_TARGET) -> None:
    """确保统一映射表存在。"""
    with conn.cursor() as cur:
        cur.execute(
            f"""
CREATE TABLE IF NOT EXISTS {_quote_identifier(table_name)} (
  `inter_id` varchar(32) NOT NULL COMMENT '标准路口ID',
  `cross_id` varchar(32) DEFAULT NULL COMMENT '信控机/海信路口ID',
  `plan_no` int NOT NULL COMMENT '方案号',
  `link_id` varchar(64) NOT NULL DEFAULT '' COMMENT '进口link，主辅路场景用于物理定位',
  `lane_group_id` varchar(128) NOT NULL DEFAULT '' COMMENT '车道簇ID，优先使用link-scoped key',
  `lane_nos_json` json DEFAULT NULL COMMENT '物理车道号列表',
  `cluster_kind` varchar(64) DEFAULT NULL COMMENT '车道簇类型',
  `capabilities_json` json DEFAULT NULL COMMENT '车道簇可通行能力',
  `signal_atom` varchar(64) NOT NULL COMMENT '信号放行车流，如南左',
  `source_key` varchar(32) NOT NULL COMMENT 'P{{n}}/OP{{n}}/IFL{{dir8_no}}',
  `source_type` varchar(32) NOT NULL DEFAULT '' COMMENT 'phase/overlap/inferred_follow',
  `release_kind` varchar(32) NOT NULL COMMENT 'MAIN/OVERLAP/INFERRED_FOLLOW',
  `dir8_no` int DEFAULT NULL COMMENT '1基八方向',
  `turn_dir_no` int DEFAULT NULL COMMENT '标准转向编码',
  `movement_key` varchar(160) NOT NULL COMMENT '优化器movement键',
  `stage_nos_json` json DEFAULT NULL COMMENT '标准stage_no列表',
  `parent_source_keys_json` json DEFAULT NULL COMMENT 'OP/IFL的父级主相位',
  `is_active_green` tinyint NOT NULL DEFAULT 1 COMMENT '阶段内是否实际绿灯放行',
  `included_phase_nos_json` json DEFAULT NULL COMMENT '仅OVERLAP使用',
  `modifier_phase_nos_json` json DEFAULT NULL COMMENT '仅OVERLAP使用',
  `confidence` varchar(32) NOT NULL DEFAULT 'low',
  `score` int DEFAULT NULL,
  `evidence_json` json DEFAULT NULL,
  `is_controlled` tinyint NOT NULL DEFAULT 1 COMMENT '是否参与优化消费',
  `schema_version` varchar(64) NOT NULL DEFAULT 'lane_phase_mapping_v1',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_deleted` tinyint NOT NULL DEFAULT 0,
  PRIMARY KEY (`inter_id`, `plan_no`, `lane_group_id`, `source_key`, `signal_atom`),
  KEY `idx_lpm_inter_plan_stage` (`inter_id`, `plan_no`),
  KEY `idx_lpm_source` (`inter_id`, `plan_no`, `source_key`),
  KEY `idx_lpm_movement` (`inter_id`, `plan_no`, `movement_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='plan级车道簇-信号放行单元-标准阶段统一映射表'
""".strip()
        )
    conn.commit()


def derive_lane_phase_rows(
    atom_rows: list[dict[str, Any]],
    stage_phase_rows: list[dict[str, Any]],
    stage_cfg_rows: list[dict[str, Any]],
    plan_cfg_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """由 atom-lane、stage-phase、stage flow_combo 推导统一映射行。"""
    stage_index = _build_stage_phase_index(stage_phase_rows)
    flow_index = _build_stage_flow_index(stage_cfg_rows)
    plan_atom_index = _build_plan_atom_index(plan_cfg_rows)

    output: list[dict[str, Any]] = []
    for atom in atom_rows:
        inter_id = str(atom.get("inter_id") or "")
        plan_no = _to_int(atom.get("plan_no"))
        signal_atom = str(atom.get("signal_atom") or atom.get("signalAtom") or "")
        source_key = str(atom.get("source_key") or atom.get("sourceKey") or "")
        if not inter_id or plan_no is None or not signal_atom:
            continue

        key = (inter_id, plan_no)
        stage_meta = stage_index.get((inter_id, plan_no, source_key), {})
        release_kind = _release_kind(source_key, atom.get("source_type"))
        source_type = _source_type(source_key, atom.get("source_type"))
        stage_nos = list(stage_meta.get("stage_nos") or [])
        parent_source_keys: list[str] = []
        included_phase_nos = list(stage_meta.get("included_phase_nos") or [])
        modifier_phase_nos = list(stage_meta.get("modifier_phase_nos") or [])
        is_active_green = 1 if stage_meta.get("is_active_green", bool(stage_nos)) else 0
        evidence_notes: list[str] = []

        if release_kind == "OVERLAP":
            parent_source_keys = _phase_nos_to_source_keys(included_phase_nos + modifier_phase_nos)
        elif release_kind == "INFERRED_FOLLOW":
            ifl = _derive_inferred_follow_stage_and_parent(
                atom,
                stage_index=stage_index,
                flow_index=flow_index,
                plan_atoms=plan_atom_index.get(key, {}),
            )
            stage_nos = ifl["stage_nos"]
            parent_source_keys = ifl["parent_source_keys"]
            is_active_green = 1 if stage_nos else 0
            evidence_notes.extend(ifl["evidence"])
        else:
            parent_source_keys = []

        confidence = _derive_confidence(
            atom.get("confidence"),
            release_kind=release_kind,
            stage_nos=stage_nos,
            parent_source_keys=parent_source_keys,
        )
        evidence = _merge_evidence(atom.get("evidence_json"), evidence_notes)
        if release_kind in {"MAIN", "OVERLAP"} and not stage_nos:
            evidence.append("no_stage_phase_relation")

        row = {
            "inter_id": inter_id,
            "cross_id": atom.get("cross_id"),
            "plan_no": plan_no,
            "link_id": atom.get("link_id") or "",
            "lane_group_id": atom.get("lane_group_id") or "",
            "lane_nos_json": _json_array(atom.get("lane_nos_json")),
            "cluster_kind": atom.get("cluster_kind") or "",
            "capabilities_json": _json_array(atom.get("capabilities_json")),
            "signal_atom": signal_atom,
            "source_key": source_key,
            "source_type": source_type,
            "release_kind": release_kind,
            "dir8_no": _to_int(atom.get("dir8_no") if "dir8_no" in atom else atom.get("dir8No")),
            "turn_dir_no": _to_int(atom.get("turn_dir_no") if "turn_dir_no" in atom else atom.get("turnDirNo")),
            "movement_key": atom.get("movement_key") or movement_key_for_atom(signal_atom, source_key),
            "stage_nos_json": _json_dumps(stage_nos),
            "parent_source_keys_json": _json_dumps(parent_source_keys),
            "is_active_green": is_active_green,
            "included_phase_nos_json": _json_dumps(included_phase_nos),
            "modifier_phase_nos_json": _json_dumps(modifier_phase_nos),
            "confidence": confidence,
            "score": atom.get("score") or 0,
            "evidence_json": _json_dumps(evidence),
            "is_controlled": _is_controlled(atom, confidence),
            "schema_version": SCHEMA_VERSION,
            "is_deleted": 0,
        }
        output.append(row)
    return output


def build_rows(
    conn: Any,
    *,
    inter_id: str | None = None,
    plan_no: int | None = None,
    atom_table: str = TABLE_ATOM_LANE_MAPPING,
) -> list[dict[str, Any]]:
    atom_rows = _fetch_atom_rows(conn, inter_id=inter_id, plan_no=plan_no, table_name=atom_table)
    stage_phase_rows = _fetch_stage_phase_rows(conn, inter_id=inter_id, plan_no=plan_no)
    stage_cfg_rows = _fetch_stage_cfg_rows(conn, inter_id=inter_id)
    plan_cfg_rows = _fetch_plan_cfg_rows(conn, inter_id=inter_id, plan_no=plan_no)
    return derive_lane_phase_rows(atom_rows, stage_phase_rows, stage_cfg_rows, plan_cfg_rows)


def cleanup_existing_rows(
    conn: Any,
    *,
    target_table: str = TABLE_TARGET,
    inter_id: str | None = None,
    plan_no: int | None = None,
    truncate: bool = False,
) -> int:
    """重建前清理旧行，避免源映射变化后残留过期记录。"""
    ensure_target_table(conn, target_table)
    with conn.cursor() as cur:
        if truncate:
            cur.execute(f"TRUNCATE TABLE {_quote_identifier(target_table)}")
            affected = cur.rowcount
        else:
            filters = ["COALESCE(is_deleted, 0) = 0"]
            params: list[Any] = []
            if inter_id:
                filters.append("inter_id = %s")
                params.append(inter_id)
            if plan_no is not None:
                filters.append("plan_no = %s")
                params.append(plan_no)
            if not inter_id and plan_no is not None:
                raise ValueError("按 plan_no 清理时必须同时指定 inter_id，避免跨路口误删")
            cur.execute(
                f"""
                UPDATE {_quote_identifier(target_table)}
                SET is_deleted = 1,
                    update_time = CURRENT_TIMESTAMP
                WHERE {" AND ".join(filters)}
                """,
                params,
            )
            affected = cur.rowcount
    conn.commit()
    return affected


def upsert_rows(conn: Any, rows: list[dict[str, Any]], *, target_table: str = TABLE_TARGET) -> int:
    if not rows:
        return 0
    ensure_target_table(conn, target_table)
    columns = ", ".join(_quote_identifier(col) for col in TARGET_COLUMNS)
    placeholders = ", ".join(["%s"] * len(TARGET_COLUMNS))
    updates = ", ".join(
        f"{_quote_identifier(col)}=VALUES({_quote_identifier(col)})"
        for col in TARGET_COLUMNS
        if col not in {"inter_id", "plan_no", "lane_group_id", "source_key", "signal_atom"}
    )
    updates += ", `update_time`=CURRENT_TIMESTAMP"
    sql = (
        f"INSERT INTO {_quote_identifier(target_table)} ({columns}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )
    values = [tuple(row.get(col) for col in TARGET_COLUMNS) for row in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, values)
    conn.commit()
    return len(rows)


def run_build(
    *,
    inter_id: str | None = None,
    plan_no: int | None = None,
    atom_table: str = TABLE_ATOM_LANE_MAPPING,
    target_table: str = TABLE_TARGET,
    skip_db: bool = False,
    truncate: bool = False,
    cleanup: bool = True,
) -> dict[str, int]:
    conn = _get_mysql_connection(streaming=False)
    try:
        rows = build_rows(conn, inter_id=inter_id, plan_no=plan_no, atom_table=atom_table)
        cleaned = 0
        if not skip_db and (cleanup or truncate):
            cleaned = cleanup_existing_rows(
                conn,
                target_table=target_table,
                inter_id=inter_id,
                plan_no=plan_no,
                truncate=truncate,
            )
        upserted = 0 if skip_db else upsert_rows(conn, rows, target_table=target_table)
        counts = {"target_rows": len(rows), "upsert_rows": upserted, "cleanup_rows": cleaned}
        counts.update(quality_summary(rows))
        return counts
    finally:
        conn.close()


def quality_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    """输出生成质量统计，用于批处理验收和日志观察。"""
    counts: dict[str, int] = {}
    for row in rows:
        release_kind = str(row.get("release_kind") or "UNKNOWN").lower()
        confidence = str(row.get("confidence") or "unknown").lower()
        counts[f"release_{release_kind}"] = counts.get(f"release_{release_kind}", 0) + 1
        counts[f"confidence_{confidence}"] = counts.get(f"confidence_{confidence}", 0) + 1
        stage_nos = _json_list(row.get("stage_nos_json"))
        parent_keys = _json_list(row.get("parent_source_keys_json"))
        if not stage_nos:
            counts["rows_without_stage"] = counts.get("rows_without_stage", 0) + 1
        if row.get("release_kind") == "INFERRED_FOLLOW":
            if parent_keys:
                counts["ifl_with_parent"] = counts.get("ifl_with_parent", 0) + 1
            else:
                counts["ifl_without_parent"] = counts.get("ifl_without_parent", 0) + 1
        if row.get("release_kind") == "OVERLAP" and not parent_keys:
            counts["overlap_without_parent"] = counts.get("overlap_without_parent", 0) + 1
        if not _truthy(row.get("is_controlled")):
            counts["uncontrolled_rows"] = counts.get("uncontrolled_rows", 0) + 1
    return counts


def _build_stage_phase_index(rows: list[dict[str, Any]]) -> dict[tuple[str, int, str], dict[str, Any]]:
    index: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in rows:
        inter_id = str(row.get("inter_id") or "")
        plan_no = _to_int(row.get("plan_no"))
        source_key = str(row.get("source_key") or "")
        stage_no = _to_int(row.get("stage_no"))
        if not inter_id or plan_no is None or not source_key or stage_no is None:
            continue
        item = index.setdefault(
            (inter_id, plan_no, source_key),
            {
                "stage_nos": set(),
                "is_active_green": False,
                "included_phase_nos": set(),
                "modifier_phase_nos": set(),
            },
        )
        if _truthy(row.get("is_active_green")):
            item["stage_nos"].add(stage_no)
            item["is_active_green"] = True
        item["included_phase_nos"].update(_json_int_list(row.get("included_phase_nos_json")))
        item["modifier_phase_nos"].update(_json_int_list(row.get("modifier_phase_nos_json")))
    return {
        key: {
            "stage_nos": sorted(value["stage_nos"]),
            "is_active_green": value["is_active_green"],
            "included_phase_nos": sorted(value["included_phase_nos"]),
            "modifier_phase_nos": sorted(value["modifier_phase_nos"]),
        }
        for key, value in index.items()
    }


def _build_stage_flow_index(rows: list[dict[str, Any]]) -> dict[tuple[str, int, int], set[int]]:
    index: dict[tuple[str, int, int], set[int]] = defaultdict(set)
    for row in rows:
        inter_id = str(row.get("inter_id") or "")
        stage_no = _to_int(row.get("stage_no"))
        if not inter_id or stage_no is None:
            continue
        for flow in _json_list(row.get("flow_combo_json")):
            if not isinstance(flow, dict):
                continue
            dir8_no = _flow_dir8_no(flow)
            turn_dir_no = _flow_turn_dir_no(flow)
            if dir8_no is None or turn_dir_no is None:
                continue
            index[(inter_id, dir8_no, turn_dir_no)].add(stage_no)
    return index


def _build_plan_atom_index(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, dict[str, Any]]]:
    index: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        inter_id = str(row.get("inter_id") or "")
        plan_no = _to_int(row.get("plan_no"))
        if not inter_id or plan_no is None:
            continue
        payload = _json_obj(row.get("signal_atom_json"))
        for atom in payload.get("atoms") or []:
            if not isinstance(atom, dict):
                continue
            source_key = str(atom.get("sourceKey") or atom.get("source_key") or "")
            if source_key:
                index[(inter_id, plan_no)][source_key] = atom
    return index


def _derive_inferred_follow_stage_and_parent(
    atom: dict[str, Any],
    *,
    stage_index: dict[tuple[str, int, str], dict[str, Any]],
    flow_index: dict[tuple[str, int, int], set[int]],
    plan_atoms: dict[str, dict[str, Any]],
) -> dict[str, list[Any]]:
    inter_id = str(atom.get("inter_id") or "")
    plan_no = _to_int(atom.get("plan_no"))
    dir8_no = _to_int(atom.get("dir8_no") if "dir8_no" in atom else atom.get("dir8No"))
    if plan_no is None or dir8_no is None:
        return {"stage_nos": [], "parent_source_keys": [], "evidence": ["ifl_missing_plan_or_dir"]}

    left_stages = set(flow_index.get((inter_id, dir8_no, 1), set()))
    through_stages = set(flow_index.get((inter_id, dir8_no, 2), set()))
    stage_nos = sorted(left_stages & through_stages or left_stages)
    through_parent_keys = [
        source_key
        for source_key, parent_atom in plan_atoms.items()
        if source_key.startswith("P")
        and _to_int(parent_atom.get("dir8No") if "dir8No" in parent_atom else parent_atom.get("dir8_no")) == dir8_no
        and _standard_turn_dir_no(parent_atom.get("turnDirNo") if "turnDirNo" in parent_atom else parent_atom.get("turn_dir_no")) == 2
    ]
    active_parents: set[str] = set()
    for parent_key in through_parent_keys:
        parent_stages = set(stage_index.get((inter_id, plan_no, parent_key), {}).get("stage_nos") or [])
        if not stage_nos or parent_stages & set(stage_nos):
            active_parents.add(parent_key)

    evidence = ["if_l_stage_from_flow_combo"]
    if through_parent_keys:
        evidence.append("if_l_parent_from_same_dir_through_phase")
    if not active_parents:
        evidence.append("if_l_parent_missing")
    return {
        "stage_nos": stage_nos,
        "parent_source_keys": sorted(active_parents),
        "evidence": evidence,
    }


def _fetch_atom_rows(
    conn: Any,
    *,
    inter_id: str | None,
    plan_no: int | None,
    table_name: str,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    inter_filter = ""
    if inter_id:
        inter_filter = " AND inter_id = %s"
        params.append(inter_id)
    plan_filter = ""
    if plan_no is not None:
        plan_filter = " AND plan_no = %s"
        params.append(plan_no)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT inter_id, cross_id, plan_no, link_id, lane_group_id,
                   CAST(lane_nos_json AS CHAR) AS lane_nos_json,
                   cluster_kind,
                   CAST(capabilities_json AS CHAR) AS capabilities_json,
                   signal_atom, source_key, source_type, dir8_no, turn_dir_no,
                   movement_key, confidence, score,
                   CAST(evidence_json AS CHAR) AS evidence_json
            FROM {_quote_identifier(table_name)}
            WHERE COALESCE(is_deleted, 0) = 0
              AND plan_no IS NOT NULL
              AND COALESCE(signal_atom, '') <> ''
              {inter_filter}
              {plan_filter}
            ORDER BY inter_id, plan_no, lane_group_id, source_key, signal_atom
            """,
            params,
        )
        return list(cur.fetchall())


def _fetch_stage_phase_rows(conn: Any, *, inter_id: str | None, plan_no: int | None) -> list[dict[str, Any]]:
    params: list[Any] = []
    inter_filter = ""
    if inter_id:
        inter_filter = " AND inter_id = %s"
        params.append(inter_id)
    plan_filter = ""
    if plan_no is not None:
        plan_filter = " AND plan_no = %s"
        params.append(plan_no)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT inter_id, plan_no, stage_no, source_key, source_type,
                   is_active_green,
                   CAST(included_phase_nos_json AS CHAR) AS included_phase_nos_json,
                   CAST(modifier_phase_nos_json AS CHAR) AS modifier_phase_nos_json
            FROM {_quote_identifier(TABLE_PLAN_STAGE_PHASE_RLTN)}
            WHERE COALESCE(is_deleted, 0) = 0
              {inter_filter}
              {plan_filter}
            """,
            params,
        )
        return list(cur.fetchall())


def _fetch_stage_cfg_rows(conn: Any, *, inter_id: str | None) -> list[dict[str, Any]]:
    params: list[Any] = []
    inter_filter = ""
    if inter_id:
        inter_filter = " AND inter_id = %s"
        params.append(inter_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT inter_id, stage_no, CAST(flow_combo_json AS CHAR) AS flow_combo_json
            FROM {_quote_identifier(TABLE_STAGE_CFG)}
            WHERE COALESCE(is_deleted, 0) = 0
              {inter_filter}
            """,
            params,
        )
        return list(cur.fetchall())


def _fetch_plan_cfg_rows(conn: Any, *, inter_id: str | None, plan_no: int | None) -> list[dict[str, Any]]:
    params: list[Any] = []
    inter_filter = ""
    if inter_id:
        inter_filter = " AND inter_id = %s"
        params.append(inter_id)
    plan_filter = ""
    if plan_no is not None:
        plan_filter = " AND plan_no = %s"
        params.append(plan_no)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT inter_id, plan_no, CAST(signal_atom_json AS CHAR) AS signal_atom_json
            FROM {_quote_identifier(TABLE_PLAN_CFG)}
            WHERE COALESCE(is_deleted, 0) = 0
              AND signal_atom_json IS NOT NULL
              {inter_filter}
              {plan_filter}
            """,
            params,
        )
        return list(cur.fetchall())


def _release_kind(source_key: str, source_type: Any) -> str:
    if source_key.startswith("OP"):
        return "OVERLAP"
    if source_key.startswith("IFL"):
        return "INFERRED_FOLLOW"
    if source_key.startswith("P"):
        return "MAIN"
    text = str(source_type or "").lower()
    if "overlap" in text:
        return "OVERLAP"
    if "inferred" in text:
        return "INFERRED_FOLLOW"
    return "MAIN"


def _source_type(source_key: str, source_type: Any) -> str:
    if source_key.startswith("OP"):
        return "overlap"
    if source_key.startswith("IFL"):
        return "inferred_follow"
    if source_key.startswith("P"):
        return "phase"
    return str(source_type or "").lower()


def _derive_confidence(
    raw_confidence: Any,
    *,
    release_kind: str,
    stage_nos: list[int],
    parent_source_keys: list[str],
) -> str:
    confidence = str(raw_confidence or "low").lower()
    if confidence not in {"high", "medium", "low", "blocked"}:
        confidence = "low"
    if release_kind in {"MAIN", "OVERLAP"} and not stage_nos:
        return "blocked"
    if release_kind == "INFERRED_FOLLOW":
        if not stage_nos:
            return "blocked"
        if not parent_source_keys and confidence == "high":
            return "medium"
        if not parent_source_keys:
            return "low"
    return confidence


def _is_controlled(atom: dict[str, Any], confidence: str) -> int:
    if confidence == "blocked":
        return 0
    source_key = str(atom.get("source_key") or atom.get("sourceKey") or "")
    turn_dir_no = _to_int(atom.get("turn_dir_no") if "turn_dir_no" in atom else atom.get("turnDirNo"))
    if turn_dir_no == 3 and not source_key:
        return 0
    return 1


def _merge_evidence(raw: Any, notes: list[str]) -> list[Any]:
    parsed = _parse_json(raw)
    if isinstance(parsed, list):
        evidence = list(parsed)
    elif isinstance(parsed, dict):
        evidence = [parsed]
    elif parsed is None:
        evidence = []
    else:
        evidence = [parsed]
    evidence.extend(note for note in notes if note)
    return evidence


def _phase_nos_to_source_keys(values: list[int]) -> list[str]:
    return [f"P{phase_no}" for phase_no in sorted({value for value in values if value > 0})]


def _flow_dir8_no(flow: dict[str, Any]) -> int | None:
    return dir8_no_from_flow_combo_item(flow)


def _flow_turn_dir_no(flow: dict[str, Any]) -> int | None:
    if "turnDirNo" in flow or "turn_dir_no" in flow:
        return _standard_turn_dir_no(flow.get("turnDirNo") if "turnDirNo" in flow else flow.get("turn_dir_no"))
    flow_type_no = _to_int(flow.get("flow_type_no"))
    if flow_type_no == 1:
        return 2
    if flow_type_no == 2:
        return 1
    if flow_type_no == 3:
        return 3
    if flow_type_no == 4:
        return 1
    return None


def _standard_turn_dir_no(value: Any) -> int | None:
    turn_dir_no = _to_int(value)
    if turn_dir_no in {0, 1}:
        return 1
    if turn_dir_no in {2, 3}:
        return turn_dir_no
    return None


def _json_array(raw: Any) -> str:
    value = _parse_json(raw)
    if isinstance(value, list):
        return _json_dumps(value)
    if value in (None, ""):
        return "[]"
    return _json_dumps([value])


def _json_list(raw: Any) -> list[Any]:
    value = _parse_json(raw)
    return value if isinstance(value, list) else []


def _json_obj(raw: Any) -> dict[str, Any]:
    value = _parse_json(raw)
    return value if isinstance(value, dict) else {}


def _json_int_list(raw: Any) -> list[int]:
    values = _json_list(raw)
    ints: list[int] = []
    for value in values:
        parsed = _to_int(value)
        if parsed is not None:
            ints.append(parsed)
    return ints


def _parse_json(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return raw
    return raw


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "none", "null"}
    return bool(value)


def main() -> None:
    try:
        from env import load_project_env

        load_project_env()
    except ModuleNotFoundError:
        pass
    parser = argparse.ArgumentParser(description="生成 plan 级车道簇-相位-阶段统一映射表")
    parser.add_argument("--inter-id", help="可选，仅处理指定路口")
    parser.add_argument("--plan-no", type=int, help="可选，仅处理指定方案号；需配合 --inter-id 清理旧行")
    parser.add_argument("--atom-table", default=TABLE_ATOM_LANE_MAPPING, help="输入 atom-lane 映射表名")
    parser.add_argument("--target-table", default=TABLE_TARGET, help="目标统一映射表名")
    parser.add_argument("--skip-db", action="store_true", help="仅推导和统计，不写入 MySQL")
    parser.add_argument("--no-cleanup", action="store_true", help="写入前不软删除目标范围旧行")
    parser.add_argument("--truncate", action="store_true", help="写入前清空目标表")
    args = parser.parse_args()
    counts = run_build(
        inter_id=args.inter_id,
        plan_no=args.plan_no,
        atom_table=args.atom_table,
        target_table=args.target_table,
        skip_db=args.skip_db,
        cleanup=not args.no_cleanup,
        truncate=args.truncate,
    )
    for key, value in sorted(counts.items()):
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
