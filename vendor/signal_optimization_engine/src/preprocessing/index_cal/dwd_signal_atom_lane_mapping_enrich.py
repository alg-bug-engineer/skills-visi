#!/usr/bin/env python3
"""完善 dwd_ctl_inter_signal_atom_lane_mapping 的信号车流、相位来源与车道号映射。"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Any

from data.pg_reader import connect_pg, fetch_channelization
from preprocessing.index_cal.inter_turn_5min_his_mm import ensure_atom_lane_mapping_extensions
from preprocessing.timing.atom_lane_mapping import (
    collect_fallback_lane_nos,
    movement_key_for_atom,
    resolve_atom_lane_mapping,
)
from preprocessing.timing.lane_cluster import build_lane_groups
from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_TARGET = "dwd_ctl_inter_signal_atom_lane_mapping"
TABLE_PLAN_CFG = "dwd_ctl_inter_plan_cfg"
SCHEMA_VERSION = "atom_lane_mapping_v1"


def _standard_turn_dir_no(value: Any) -> int | None:
    try:
        turn_dir_no = int(value)
    except (TypeError, ValueError):
        return None
    if turn_dir_no in {0, 1}:
        return 1
    if turn_dir_no in {2, 3}:
        return turn_dir_no
    return None


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def sync_atoms_from_plan_cfg(
    conn: Any,
    *,
    inter_id: str | None = None,
    plan_table: str = TABLE_PLAN_CFG,
    table_name: str = TABLE_TARGET,
) -> dict[str, int]:
    """从 dwd_ctl_inter_plan_cfg.signal_atom_json 同步信号原子与相位来源字段。"""
    params: list[Any] = []
    inter_filter = ""
    if inter_id:
        inter_filter = " AND inter_id = %s"
        params.append(inter_id)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT inter_id, cross_id, plan_no, signal_atom_json
            FROM {_quote_identifier(plan_table)}
            WHERE COALESCE(is_deleted, 0) = 0
              AND signal_atom_json IS NOT NULL
              AND signal_atom_json <> ''
              {inter_filter}
            ORDER BY inter_id, plan_no
            """,
            params,
        )
        plans = list(cur.fetchall())

    inserted = 0
    updated = 0
    for plan in plans:
        payload = plan.get("signal_atom_json")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                continue
        atoms = (payload or {}).get("atoms") or []
        if not atoms:
            continue

        iid = str(plan.get("inter_id") or "")
        cross_id = plan.get("cross_id")
        plan_no = _to_int(plan.get("plan_no"))
        if not iid or plan_no is None:
            continue

        for atom in atoms:
            signal_atom = str(atom.get("signalAtom") or "")
            source_key = str(atom.get("sourceKey") or "")
            if not signal_atom:
                continue
            row = {
                "signal_atom": signal_atom,
                "source_key": source_key,
                "source_type": atom.get("sourceType") or "",
                "vendor_tag": atom.get("vendorTag") or "",
                "dir8_no": atom.get("dir8No"),
                "turn_dir_no": _standard_turn_dir_no(atom.get("turnDirNo")),
                "movement_key": movement_key_for_atom(signal_atom, source_key),
            }
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT 1
                    FROM {_quote_identifier(table_name)}
                    WHERE inter_id = %s
                      AND plan_no = %s
                      AND signal_atom = %s
                      AND COALESCE(source_key, '') = %s
                      AND COALESCE(is_deleted, 0) = 0
                    LIMIT 1
                    """,
                    (iid, plan_no, signal_atom, source_key),
                )
                exists = cur.fetchone() is not None

            if exists:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        UPDATE {_quote_identifier(table_name)}
                        SET cross_id = COALESCE(%s, cross_id),
                            source_type = %s,
                            vendor_tag = %s,
                            dir8_no = %s,
                            turn_dir_no = %s,
                            movement_key = %s,
                            schema_version = %s,
                            update_time = CURRENT_TIMESTAMP
                        WHERE inter_id = %s
                          AND plan_no = %s
                          AND signal_atom = %s
                          AND COALESCE(source_key, '') = %s
                          AND COALESCE(is_deleted, 0) = 0
                        """,
                        (
                            cross_id,
                            row["source_type"],
                            row["vendor_tag"],
                            row["dir8_no"],
                            row["turn_dir_no"],
                            row["movement_key"],
                            SCHEMA_VERSION,
                            iid,
                            plan_no,
                            signal_atom,
                            source_key,
                        ),
                    )
                    updated += cur.rowcount
            else:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        INSERT INTO {_quote_identifier(table_name)} (
                            inter_id, cross_id, plan_no, stage_no,
                            signal_atom, source_key, source_type, vendor_tag,
                            dir8_no, turn_dir_no, link_id, lane_group_id,
                            lane_nos_json, cluster_kind, capabilities_json,
                            movement_key, confidence, score, evidence_json,
                            flow_green_check_json, schema_version,
                            create_time, update_time, is_deleted
                        ) VALUES (
                            %s, %s, %s, NULL,
                            %s, %s, %s, %s,
                            %s, %s, NULL, NULL,
                            '[]', NULL, '[]',
                            %s, 'low', 0, %s,
                            %s, %s,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0
                        )
                        """,
                        (
                            iid,
                            cross_id,
                            plan_no,
                            row["signal_atom"],
                            row["source_key"],
                            row["source_type"],
                            row["vendor_tag"],
                            row["dir8_no"],
                            row["turn_dir_no"],
                            row["movement_key"],
                            json.dumps(["synced_from_plan_cfg"], ensure_ascii=False),
                            "{}",
                            SCHEMA_VERSION,
                        ),
                    )
                    inserted += 1

    conn.commit()
    return {"sync_inserted": inserted, "sync_updated": updated, "sync_plans": len(plans)}


def enrich_rows(
    conn: Any,
    pg_conn: Any,
    *,
    inter_id: str | None = None,
    table_name: str = TABLE_TARGET,
) -> dict[str, int]:
    ensure_atom_lane_mapping_extensions(conn, table_name)
    rows = _fetch_atom_rows(conn, inter_id=inter_id, table_name=table_name)
    updates: list[tuple[Any, ...]] = []
    lane_groups_by_inter: dict[str, list[dict[str, Any]]] = {}
    stats: dict[str, int] = defaultdict(int)

    for row in rows:
        iid = str(row.get("inter_id") or "")
        if iid not in lane_groups_by_inter:
            channelization = fetch_channelization(pg_conn, iid)
            lane_groups_by_inter[iid] = build_lane_groups(channelization)
            if lane_groups_by_inter[iid]:
                stats["intersections_with_channelization"] += 1
            else:
                stats["intersections_without_channelization"] += 1

        atom_payload = {
            "signalAtom": row.get("signal_atom") or row.get("signalAtom"),
            "sourceKey": row.get("source_key") or row.get("sourceKey"),
            "dir8No": row.get("dir8_no") or row.get("dir8No"),
            "turnDirNo": row.get("turn_dir_no") or row.get("turnDirNo"),
        }
        mapping = resolve_atom_lane_mapping(atom_payload, lane_groups_by_inter[iid]).to_dict()
        lane_group_ids = mapping.get("laneGroupIds") or []
        lane_nos = [int(x) for x in mapping.get("laneNos") or []]
        method = str(mapping.get("method") or "")
        evidence = list(mapping.get("evidence") or [])

        if not lane_nos:
            fallback_lane_nos = collect_fallback_lane_nos(atom_payload, lane_groups_by_inter[iid])
            if fallback_lane_nos:
                lane_nos = fallback_lane_nos
                method = "fallback_lane_nos_by_turn"
                evidence.append("fallback_lane_nos_by_turn")
                if mapping.get("confidence") == "low":
                    mapping["confidence"] = "medium"

        first_group = _group_by_key(lane_groups_by_inter[iid], lane_group_ids[0] if lane_group_ids else "")
        if lane_nos:
            stats["rows_with_lane_nos"] += 1
        else:
            stats["rows_without_lane_nos"] += 1
        stats[f"confidence_{mapping.get('confidence') or 'unknown'}"] += 1

        updates.append(
            (
                first_group.get("linkId") if first_group else None,
                lane_group_ids[0] if lane_group_ids else None,
                json.dumps(lane_nos, ensure_ascii=False),
                first_group.get("clusterKind") if first_group else None,
                json.dumps(first_group.get("capabilities") if first_group else [], ensure_ascii=False),
                mapping.get("confidence") or "unmapped",
                mapping.get("score") or 0,
                json.dumps(
                    {
                        **mapping,
                        "method": method,
                        "evidence": evidence,
                    },
                    ensure_ascii=False,
                ),
                row.get("inter_id"),
                row.get("plan_no"),
                row.get("signal_atom"),
                row.get("source_key"),
            )
        )

    if updates:
        with conn.cursor() as cur:
            cur.executemany(
                f"""
                UPDATE {_quote_identifier(table_name)}
                SET link_id = %s,
                    lane_group_id = %s,
                    lane_nos_json = %s,
                    cluster_kind = %s,
                    capabilities_json = %s,
                    confidence = %s,
                    score = %s,
                    evidence_json = %s,
                    schema_version = %s,
                    update_time = CURRENT_TIMESTAMP
                WHERE inter_id = %s
                  AND plan_no = %s
                  AND signal_atom = %s
                  AND COALESCE(source_key, '') = COALESCE(%s, '')
                  AND COALESCE(is_deleted, 0) = 0
                """,
                [(*item[:8], SCHEMA_VERSION, *item[8:]) for item in updates],
            )
        conn.commit()

    stats["enrich_updated"] = len(updates)
    stats["enrich_total_rows"] = len(rows)
    return dict(stats)


def run_enrich(
    *,
    inter_id: str | None = None,
    target_table: str = TABLE_TARGET,
    plan_table: str = TABLE_PLAN_CFG,
    skip_sync: bool = False,
) -> dict[str, int]:
    conn = _get_mysql_connection(streaming=False)
    pg_conn = connect_pg()
    try:
        counts: dict[str, int] = {}
        if not skip_sync:
            counts.update(
                sync_atoms_from_plan_cfg(
                    conn,
                    inter_id=inter_id,
                    plan_table=plan_table,
                    table_name=target_table,
                )
            )
        counts.update(
            enrich_rows(conn, pg_conn, inter_id=inter_id, table_name=target_table)
        )
        return counts
    finally:
        conn.close()
        pg_conn.close()


def _fetch_atom_rows(conn: Any, *, inter_id: str | None, table_name: str) -> list[dict[str, Any]]:
    params: list[Any] = []
    inter_filter = ""
    if inter_id:
        inter_filter = " AND inter_id = %s"
        params.append(inter_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT inter_id, plan_no, signal_atom, source_key, source_type,
                   vendor_tag, dir8_no, turn_dir_no
            FROM {_quote_identifier(table_name)}
            WHERE COALESCE(is_deleted, 0) = 0{inter_filter}
            ORDER BY inter_id, plan_no, signal_atom, source_key
            """,
            params,
        )
        return list(cur.fetchall())


def _group_by_key(groups: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    for group in groups:
        if group.get("laneGroupKey") == key or group.get("laneGroupId") == key:
            return group
    return None


def main() -> None:
    try:
        from env import load_project_env

        load_project_env()
    except ModuleNotFoundError:
        pass
    parser = argparse.ArgumentParser(description="完善 signal atom 到车道组映射")
    parser.add_argument("--inter-id", help="可选，仅处理指定路口")
    parser.add_argument("--target-table", default=TABLE_TARGET)
    parser.add_argument("--plan-table", default=TABLE_PLAN_CFG)
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="跳过从 plan_cfg.signal_atom_json 同步信号原子字段",
    )
    args = parser.parse_args()
    counts = run_enrich(
        inter_id=args.inter_id,
        target_table=args.target_table,
        plan_table=args.plan_table,
        skip_sync=args.skip_sync,
    )
    for key, value in sorted(counts.items()):
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
