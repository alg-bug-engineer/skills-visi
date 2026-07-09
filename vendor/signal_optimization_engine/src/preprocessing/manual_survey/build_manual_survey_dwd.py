#!/usr/bin/env python3
"""从 ODS 生成 DWD：路网匹配 + 问题类型展开 + 路口时段聚合。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from env import load_project_env  # noqa: E402

load_project_env()

from preprocessing.complaint.inter_match import load_inter_catalog, match_location_to_inter  # noqa: E402
from preprocessing.manual_survey.schema import CREATE_DWD_ISSUE_DDL, TABLE_DWD_ISSUE  # noqa: E402
from preprocessing.manual_survey.taxonomy import split_problem_types, validate_problem_type  # noqa: E402
from preprocessing.timing.timing_csv_to_stage_table import (  # noqa: E402
    _build_upsert_sql,
    _get_mysql_connection,
)

DWD_COLUMNS = [
    "source_key",
    "inter_id",
    "inter_name",
    "survey_batch",
    "time_period",
    "problem_type",
    "problem_primary_flag",
    "issue_record_cnt",
    "problem_desc",
    "survey_point_ids",
    "inter_name_raw",
    "survey_lon",
    "survey_lat",
    "match_method",
    "match_status",
    "match_distance_m",
    "roadnet_lon",
    "roadnet_lat",
    "source_file",
]


def _fetch_ods(conn, survey_batch: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT record_key, survey_batch, survey_point_id, inter_name_raw,
                   time_period, problem_primary, problem_full_text, problem_desc,
                   lon, lat, source_file
            FROM ods_ctl_inter_manual_survey_issue_raw
            WHERE survey_batch = %s
            ORDER BY survey_point_id, time_period, record_key
            """,
            (survey_batch,),
        )
        return list(cur.fetchall())


def _expand_and_aggregate(
    ods_rows: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    *,
    survey_batch: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    match_report: list[dict[str, Any]] = []
    point_match_cache: dict[str, dict[str, Any]] = {}

    for row in ods_rows:
        spid = row["survey_point_id"]
        if spid not in point_match_cache:
            match = match_location_to_inter(
                location_text=row["inter_name_raw"],
                lon=row.get("lon"),
                lat=row.get("lat"),
                catalog=catalog,
            )
            point_match_cache[spid] = match
            match_report.append(
                {
                    "survey_point_id": spid,
                    "inter_name_raw": row["inter_name_raw"],
                    "inter_id": match.get("inter_id") or "",
                    "inter_name": match.get("inter_name") or "",
                    "match_method": match.get("match_method") or "",
                    "match_status": match.get("match_status") or "",
                    "match_distance_m": match.get("match_distance_m") or "",
                }
            )

        match = point_match_cache[spid]
        source_key = match["inter_id"] if match.get("inter_id") else spid
        inter_name = match.get("inter_name") or row["inter_name_raw"]
        problem_types = split_problem_types(row.get("problem_full_text") or "")
        if not problem_types:
            problem_types = [row.get("problem_primary") or ""]

        for problem_type in problem_types:
            if validate_problem_type(problem_type) is None:
                continue
            gkey = (source_key, row["time_period"], problem_type)
            bucket = grouped.setdefault(
                gkey,
                {
                    "source_key": source_key,
                    "inter_id": match.get("inter_id"),
                    "inter_name": inter_name,
                    "survey_batch": survey_batch,
                    "time_period": row["time_period"],
                    "problem_type": problem_type,
                    "problem_primary_flag": 0,
                    "issue_record_cnt": 0,
                    "problem_descs": [],
                    "survey_point_ids": set(),
                    "inter_name_raw": row["inter_name_raw"],
                    "survey_lon": row.get("lon"),
                    "survey_lat": row.get("lat"),
                    "match_method": match.get("match_method"),
                    "match_status": match.get("match_status") or "pending",
                    "match_distance_m": match.get("match_distance_m"),
                    "roadnet_lon": match.get("roadnet_lon"),
                    "roadnet_lat": match.get("roadnet_lat"),
                    "source_file": row.get("source_file"),
                },
            )
            bucket["issue_record_cnt"] += 1
            desc = str(row.get("problem_desc") or "").strip()
            if desc:
                bucket["problem_descs"].append(desc)
            bucket["survey_point_ids"].add(spid)
            if row.get("problem_primary") == problem_type:
                bucket["problem_primary_flag"] = 1

    dwd_rows: list[dict[str, Any]] = []
    for bucket in grouped.values():
        descs = []
        seen: set[str] = set()
        for d in bucket["problem_descs"]:
            if d not in seen:
                seen.add(d)
                descs.append(d)
        dwd_rows.append(
            {
                "source_key": bucket["source_key"],
                "inter_id": bucket.get("inter_id"),
                "inter_name": bucket["inter_name"],
                "survey_batch": bucket["survey_batch"],
                "time_period": bucket["time_period"],
                "problem_type": bucket["problem_type"],
                "problem_primary_flag": bucket["problem_primary_flag"],
                "issue_record_cnt": bucket["issue_record_cnt"],
                "problem_desc": "；".join(descs)[:1024] or bucket["problem_type"],
                "survey_point_ids": json.dumps(
                    sorted(bucket["survey_point_ids"]), ensure_ascii=False
                ),
                "inter_name_raw": bucket.get("inter_name_raw"),
                "survey_lon": bucket.get("survey_lon"),
                "survey_lat": bucket.get("survey_lat"),
                "match_method": bucket.get("match_method"),
                "match_status": bucket.get("match_status") or "pending",
                "match_distance_m": bucket.get("match_distance_m"),
                "roadnet_lon": bucket.get("roadnet_lon"),
                "roadnet_lat": bucket.get("roadnet_lat"),
                "source_file": bucket.get("source_file"),
            }
        )
    return dwd_rows, match_report


def write_dwd(conn, rows: list[dict[str, Any]]) -> int:
    with conn.cursor() as cur:
        cur.execute(CREATE_DWD_ISSUE_DDL)
    conn.commit()
    if not rows:
        return 0
    sql = _build_upsert_sql(TABLE_DWD_ISSUE, DWD_COLUMNS)
    values = [tuple(row.get(c) for c in DWD_COLUMNS) for row in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, values)
    conn.commit()
    return len(rows)


def write_match_report(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run_build(
    *,
    survey_batch: str = "jinan_2025",
    report_path: Path | None = None,
) -> dict[str, Any]:
    conn = _get_mysql_connection()
    try:
        ods_rows = _fetch_ods(conn, survey_batch)
        if not ods_rows:
            raise RuntimeError(
                f"ODS 无数据，请先运行 import_manual_survey_ods_mysql.py (survey_batch={survey_batch})"
            )
        catalog = load_inter_catalog()
        dwd_rows, match_report = _expand_and_aggregate(
            ods_rows, catalog, survey_batch=survey_batch
        )
        n = write_dwd(conn, dwd_rows)
    finally:
        conn.close()

    if report_path:
        write_match_report(report_path, match_report)

    matched = sum(1 for r in match_report if r.get("match_status") == "matched")
    return {
        "dwd_rows": n,
        "ods_rows": len(ods_rows),
        "survey_points": len(match_report),
        "matched_points": matched,
        "total_issue_records": sum(r["issue_record_cnt"] for r in dwd_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="人工调查 ODS → DWD")
    parser.add_argument("--survey-batch", default="jinan_2025")
    parser.add_argument(
        "--match-report",
        type=Path,
        default=ROOT / "data/manual_survey_inter_match_report_jinan_2025.csv",
    )
    args = parser.parse_args()

    stats = run_build(
        survey_batch=args.survey_batch,
        report_path=args.match_report,
    )
    print(
        f"DWD 生成完成: dwd_rows={stats['dwd_rows']} ods_rows={stats['ods_rows']} "
        f"survey_points={stats['survey_points']} matched={stats['matched_points']} "
        f"issue_records={stats['total_issue_records']}"
    )


if __name__ == "__main__":
    main()
