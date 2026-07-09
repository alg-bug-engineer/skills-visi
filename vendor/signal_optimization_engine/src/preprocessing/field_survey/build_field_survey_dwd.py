#!/usr/bin/env python3
"""从 ODS 生成 DWD：路网匹配 + 图片/建议聚合。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from env import load_project_env  # noqa: E402

load_project_env()

from preprocessing.complaint.inter_match import load_inter_catalog, match_location_to_inter  # noqa: E402
from preprocessing.field_survey.schema import CREATE_DWD_ISSUE_DDL, TABLE_DWD_ISSUE  # noqa: E402
from preprocessing.field_survey.taxonomy import match_name_candidates  # noqa: E402
from preprocessing.timing.timing_csv_to_stage_table import (  # noqa: E402
    _build_upsert_sql,
    _get_mysql_connection,
)

DWD_COLUMNS = [
    "issue_key",
    "source_key",
    "inter_id",
    "inter_name",
    "report_batch",
    "section_name",
    "inter_seq",
    "inter_name_raw",
    "inter_alias",
    "issue_seq",
    "issue_category",
    "issue_type",
    "issue_desc",
    "recommendation_text",
    "image_urls",
    "recommendations_json",
    "match_method",
    "match_status",
    "match_distance_m",
    "roadnet_lon",
    "roadnet_lat",
    "source_file",
]


def _fetch_issues(conn, report_batch: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT issue_key, report_batch, section_name, inter_seq, inter_name_raw,
                   inter_alias, issue_seq, issue_category, issue_type, issue_desc,
                   recommendation_text, source_file
            FROM ods_tfc_field_survey_issue_raw
            WHERE report_batch = %s
            ORDER BY inter_seq, issue_seq, issue_key
            """,
            (report_batch,),
        )
        return list(cur.fetchall())


def _fetch_images(conn, report_batch: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT image_key, issue_key, inter_name_raw, page_no, image_seq,
                   caption_text, local_path, local_url, image_url, match_status
            FROM ods_tfc_field_survey_image_raw
            WHERE report_batch = %s
            ORDER BY page_no, image_seq
            """,
            (report_batch,),
        )
        return list(cur.fetchall())


def _fetch_recommendations(conn, report_batch: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rec_key, inter_name_raw, horizon, rec_seq, rec_text, issue_key
            FROM ods_tfc_field_survey_recommendation_raw
            WHERE report_batch = %s
            ORDER BY inter_name_raw, horizon, rec_seq
            """,
            (report_batch,),
        )
        return list(cur.fetchall())


def _build_dwd_rows(
    issues: list[dict[str, Any]],
    images: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    *,
    report_batch: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    images_by_issue: dict[str, list[dict[str, Any]]] = defaultdict(list)
    images_by_inter: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for img in images:
        issue_key = str(img.get("issue_key") or "").strip()
        inter_name = str(img.get("inter_name_raw") or "").strip()
        payload = {
            "image_key": img.get("image_key"),
            "local_path": img.get("local_path"),
            "local_url": img.get("local_url"),
            "image_url": img.get("image_url"),
            "caption": img.get("caption_text"),
            "page_no": img.get("page_no"),
            "match_status": img.get("match_status"),
        }
        if issue_key:
            images_by_issue[issue_key].append(payload)
        if inter_name:
            images_by_inter[inter_name].append(payload)

    recs_by_inter: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in recommendations:
        inter_name = str(rec.get("inter_name_raw") or "").strip()
        if not inter_name:
            continue
        recs_by_inter[inter_name].append(
            {
                "horizon": rec.get("horizon"),
                "rec_seq": rec.get("rec_seq"),
                "rec_text": rec.get("rec_text"),
                "issue_key": rec.get("issue_key"),
            }
        )

    match_cache: dict[str, dict[str, Any]] = {}
    match_report: list[dict[str, Any]] = []
    dwd_rows: list[dict[str, Any]] = []

    def _resolve_match(inter_name_raw: str, inter_alias: str | None) -> dict[str, Any]:
        if inter_name_raw in match_cache:
            return match_cache[inter_name_raw]
        best: dict[str, Any] | None = None
        tried: list[str] = []
        for candidate in match_name_candidates(inter_name_raw, inter_alias):
            tried.append(candidate)
            result = match_location_to_inter(location_text=candidate, catalog=catalog)
            if result.get("match_status") == "matched":
                best = result
                break
            if best is None:
                best = result
        best = best or {"match_status": "unmatched"}
        match_cache[inter_name_raw] = best
        match_report.append(
            {
                "inter_name_raw": inter_name_raw,
                "match_candidates": "|".join(tried),
                "inter_id": best.get("inter_id") or "",
                "inter_name": best.get("inter_name") or "",
                "match_method": best.get("match_method") or "",
                "match_status": best.get("match_status") or "",
                "match_distance_m": best.get("match_distance_m") or "",
            }
        )
        return best

    for issue in issues:
        inter_name_raw = str(issue.get("inter_name_raw") or "").strip()
        match = _resolve_match(inter_name_raw, issue.get("inter_alias"))
        issue_key = issue["issue_key"]
        source_key = match["inter_id"] if match.get("inter_id") else issue_key
        inter_name = match.get("inter_name") or inter_name_raw

        issue_images = images_by_issue.get(issue_key) or []
        if not issue_images:
            issue_images = images_by_inter.get(inter_name_raw) or []

        rec_items = recs_by_inter.get(inter_name_raw) or []
        rec_json = rec_items if rec_items else None

        dwd_rows.append(
            {
                "issue_key": issue_key,
                "source_key": source_key,
                "inter_id": match.get("inter_id"),
                "inter_name": inter_name,
                "report_batch": report_batch,
                "section_name": issue.get("section_name"),
                "inter_seq": issue.get("inter_seq"),
                "inter_name_raw": inter_name_raw,
                "inter_alias": issue.get("inter_alias"),
                "issue_seq": issue.get("issue_seq"),
                "issue_category": issue.get("issue_category"),
                "issue_type": issue.get("issue_type"),
                "issue_desc": issue.get("issue_desc"),
                "recommendation_text": issue.get("recommendation_text"),
                "image_urls": json.dumps(issue_images, ensure_ascii=False) if issue_images else None,
                "recommendations_json": json.dumps(rec_json, ensure_ascii=False) if rec_json else None,
                "match_method": match.get("match_method"),
                "match_status": match.get("match_status") or "pending",
                "match_distance_m": match.get("match_distance_m"),
                "roadnet_lon": match.get("roadnet_lon"),
                "roadnet_lat": match.get("roadnet_lat"),
                "source_file": issue.get("source_file"),
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
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        unique[row["inter_name_raw"]] = row
    deduped = sorted(unique.values(), key=lambda r: r["inter_name_raw"])
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(deduped[0].keys()))
        writer.writeheader()
        writer.writerows(deduped)


def run_build(
    *,
    report_batch: str = "jinan_20260609",
    report_path: Path | None = None,
) -> dict[str, Any]:
    conn = _get_mysql_connection()
    try:
        issues = _fetch_issues(conn, report_batch)
        if not issues:
            raise RuntimeError(
                f"ODS 无数据，请先运行 field-survey-import (report_batch={report_batch})"
            )
        images = _fetch_images(conn, report_batch)
        recommendations = _fetch_recommendations(conn, report_batch)
        catalog = load_inter_catalog()
        dwd_rows, match_report = _build_dwd_rows(
            issues,
            images,
            recommendations,
            catalog,
            report_batch=report_batch,
        )
        n = write_dwd(conn, dwd_rows)
    finally:
        conn.close()

    if report_path:
        write_match_report(report_path, match_report)

    matched = sum(1 for r in match_report if r.get("match_status") == "matched")
    unique_inters = len({r["inter_name_raw"] for r in match_report})
    return {
        "dwd_rows": n,
        "issue_rows": len(issues),
        "image_rows": len(images),
        "intersections": unique_inters,
        "matched_intersections": matched,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="交通组织调研 ODS → DWD")
    parser.add_argument("--report-batch", default="jinan_20260609")
    parser.add_argument(
        "--match-report",
        type=Path,
        default=ROOT / "data/field_survey/jinan_20260609/match_report.csv",
    )
    args = parser.parse_args()

    stats = run_build(report_batch=args.report_batch, report_path=args.match_report)
    print(
        f"DWD 生成完成: dwd_rows={stats['dwd_rows']} issue_rows={stats['issue_rows']} "
        f"intersections={stats['intersections']} matched={stats['matched_intersections']}"
    )


if __name__ == "__main__":
    main()
