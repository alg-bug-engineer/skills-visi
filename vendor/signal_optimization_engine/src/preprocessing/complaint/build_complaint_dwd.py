#!/usr/bin/env python3
"""从 ODS 生成 DWD：路网匹配 + 投诉类型展开 + 核心问题描述。"""

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
from preprocessing.complaint.llm_summary import summarize_core_problem  # noqa: E402
from preprocessing.complaint.schema import CREATE_DWD_ISSUE_DDL, TABLE_DWD_ISSUE  # noqa: E402
from preprocessing.complaint.taxonomy import classify_complaint_type  # noqa: E402
from preprocessing.timing.timing_csv_to_stage_table import (  # noqa: E402
    _build_upsert_sql,
    _get_mysql_connection,
)

DWD_COLUMNS = [
    "source_key",
    "inter_id",
    "inter_name",
    "stat_period",
    "complaint_type",
    "complaint_count",
    "core_problem_desc",
    "district_name",
    "location_text",
    "location_key",
    "match_method",
    "match_status",
    "source_summary",
]


def _fetch_ods(conn, stat_period: str) -> tuple[list[dict], dict[str, dict]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT location_key, stat_period, report_seq, district_name, location_text,
                   complaint_count, summary_text, issue_items_json
            FROM ods_tfc_complaint_location_report_raw
            WHERE stat_period = %s
            ORDER BY report_seq
            """,
            (stat_period,),
        )
        reports = cur.fetchall()
        cur.execute(
            """
            SELECT location_key, geocode_name, geocode_method, lon, lat
            FROM ods_tfc_complaint_location_geocode_raw
            WHERE stat_period = %s
            """,
            (stat_period,),
        )
        geocodes = {row["location_key"]: row for row in cur.fetchall()}
    for row in reports:
        raw = row.get("issue_items_json")
        if isinstance(raw, str):
            row["issue_items_json"] = json.loads(raw)
        elif raw is None:
            row["issue_items_json"] = []
    return reports, geocodes


def _expand_issue_rows(
    reports: list[dict],
    geocodes: dict[str, dict],
    catalog: list[dict],
    *,
    stat_period: str,
) -> tuple[list[dict], list[dict]]:
    """按 (source_key, complaint_type) 聚合前的中间行 + 匹配报告。"""
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    match_report: list[dict] = []

    for report in reports:
        lk = report["location_key"]
        geo = geocodes.get(lk, {})
        match = match_location_to_inter(
            location_text=report["location_text"],
            geocode_name=str(geo.get("geocode_name") or ""),
            lon=geo.get("lon"),
            lat=geo.get("lat"),
            catalog=catalog,
        )
        match_report.append(
            {
                "location_key": lk,
                "location_text": report["location_text"],
                "district_name": report["district_name"],
                "inter_id": match.get("inter_id") or "",
                "inter_name": match.get("inter_name") or "",
                "match_method": match.get("match_method") or "",
                "match_status": match.get("match_status") or "",
                "match_distance_m": match.get("match_distance_m") or "",
            }
        )
        source_key = match["inter_id"] if match.get("inter_id") else lk
        items = report.get("issue_items_json") or []
        if not items:
            ctype = classify_complaint_type(report.get("summary_text") or "")
            gkey = (source_key, stat_period, ctype)
            bucket = grouped.setdefault(
                gkey,
                {
                    "source_key": source_key,
                    "inter_id": match.get("inter_id"),
                    "inter_name": match.get("inter_name") or report["location_text"],
                    "stat_period": stat_period,
                    "complaint_type": ctype,
                    "complaint_count": 0,
                    "source_texts": [],
                    "district_name": report["district_name"],
                    "location_text": report["location_text"],
                    "location_key": lk,
                    "match_method": match.get("match_method"),
                    "match_status": match.get("match_status") or "pending",
                },
            )
            bucket["complaint_count"] += int(report.get("complaint_count") or 0)
            bucket["source_texts"].append(report.get("summary_text") or "")
            continue

        for item in items:
            ctype = classify_complaint_type(item.get("topic_raw") or item.get("text") or "")
            gkey = (source_key, stat_period, ctype)
            bucket = grouped.setdefault(
                gkey,
                {
                    "source_key": source_key,
                    "inter_id": match.get("inter_id"),
                    "inter_name": match.get("inter_name") or report["location_text"],
                    "stat_period": stat_period,
                    "complaint_type": ctype,
                    "complaint_count": 0,
                    "source_texts": [],
                    "district_name": report["district_name"],
                    "location_text": report["location_text"],
                    "location_key": lk,
                    "match_method": match.get("match_method"),
                    "match_status": match.get("match_status") or "pending",
                },
            )
            bucket["complaint_count"] += int(item.get("count") or 0)
            bucket["source_texts"].append(item.get("text") or item.get("topic_raw") or "")

    return list(grouped.values()), match_report


def build_dwd_rows(grouped: list[dict], *, use_llm: bool = True) -> list[dict]:
    rows: list[dict] = []
    for item in grouped:
        core = summarize_core_problem(
            inter_name=item["inter_name"],
            complaint_type=item["complaint_type"],
            source_texts=item["source_texts"],
            complaint_count=item["complaint_count"],
        ) if use_llm else ""
        if not core:
            from preprocessing.complaint.llm_summary import _summarize_fallback

            core = _summarize_fallback(
                item["inter_name"],
                item["complaint_type"],
                "\n".join(item["source_texts"]),
                item["complaint_count"],
            )
        rows.append(
            {
                "source_key": item["source_key"],
                "inter_id": item.get("inter_id"),
                "inter_name": item["inter_name"],
                "stat_period": item["stat_period"],
                "complaint_type": item["complaint_type"],
                "complaint_count": item["complaint_count"],
                "core_problem_desc": core[:512],
                "district_name": item.get("district_name"),
                "location_text": item.get("location_text"),
                "location_key": item.get("location_key"),
                "match_method": item.get("match_method"),
                "match_status": item.get("match_status") or "pending",
                "source_summary": "\n".join(item["source_texts"])[:4000],
            }
        )
    return rows


def write_dwd(conn, rows: list[dict]) -> int:
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


def write_match_report(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run_build(*, stat_period: str = "2025", use_llm: bool = True, report_path: Path | None = None) -> dict[str, Any]:
    conn = _get_mysql_connection()
    try:
        reports, geocodes = _fetch_ods(conn, stat_period)
        if not reports:
            raise RuntimeError(f"ODS 无数据，请先运行 import_complaint_ods_mysql.py (stat_period={stat_period})")
        catalog = load_inter_catalog()
        grouped, match_report = _expand_issue_rows(reports, geocodes, catalog, stat_period=stat_period)
        dwd_rows = build_dwd_rows(grouped, use_llm=use_llm)
        n = write_dwd(conn, dwd_rows)
    finally:
        conn.close()

    if report_path:
        write_match_report(report_path, match_report)

    matched = sum(1 for r in match_report if r.get("match_status") == "matched")
    return {
        "dwd_rows": n,
        "locations": len(reports),
        "matched_locations": matched,
        "total_complaint_count": sum(r["complaint_count"] for r in dwd_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="投诉 ODS → DWD")
    parser.add_argument("--stat-period", default="2025")
    parser.add_argument("--no-llm", action="store_true", help="跳过大模型，使用规则摘要")
    parser.add_argument(
        "--match-report",
        type=Path,
        default=ROOT / "data/complaint_inter_match_report_2025.csv",
    )
    args = parser.parse_args()

    stats = run_build(
        stat_period=args.stat_period,
        use_llm=not args.no_llm,
        report_path=args.match_report,
    )
    print(
        f"DWD 生成完成: rows={stats['dwd_rows']} locations={stats['locations']} "
        f"matched={stats['matched_locations']} total_count={stats['total_complaint_count']}"
    )


if __name__ == "__main__":
    main()
