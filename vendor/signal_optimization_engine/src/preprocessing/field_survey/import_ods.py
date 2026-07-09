"""交通组织调研 PDF → MySQL ODS 导入。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from preprocessing.field_survey.parse_pdf_report import parse_pdf_report
from preprocessing.field_survey.schema import (
    ALL_DDL,
    TABLE_ODS_IMAGE,
    TABLE_ODS_ISSUE,
    TABLE_ODS_MATRIX,
    TABLE_ODS_RECOMMENDATION,
)
from preprocessing.timing.timing_csv_to_stage_table import (
    _build_upsert_sql,
    _get_mysql_connection,
)

logger = logging.getLogger(__name__)

ISSUE_COLUMNS = [
    "issue_key",
    "report_batch",
    "section_no",
    "section_name",
    "inter_seq",
    "inter_name_raw",
    "inter_alias",
    "issue_seq",
    "issue_category",
    "issue_type",
    "issue_desc",
    "recommendation_text",
    "source_page_start",
    "source_page_end",
    "source_file",
]

IMAGE_COLUMNS = [
    "image_key",
    "report_batch",
    "issue_key",
    "inter_name_raw",
    "page_no",
    "image_seq",
    "caption_text",
    "local_path",
    "local_url",
    "minio_bucket",
    "minio_object_key",
    "image_url",
    "width",
    "height",
    "file_size",
    "match_status",
    "source_file",
]

REC_COLUMNS = [
    "rec_key",
    "report_batch",
    "inter_name_raw",
    "horizon",
    "rec_seq",
    "rec_text",
    "issue_key",
    "source_file",
]

MATRIX_COLUMNS = [
    "matrix_key",
    "report_batch",
    "inter_seq",
    "inter_name_raw",
    "section_name",
    "flag_json",
    "issue_type_cnt",
    "source_file",
]


def ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        for ddl in ALL_DDL:
            cur.execute(ddl)
    conn.commit()


def _upsert(conn, table: str, columns: list[str], rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = _build_upsert_sql(table, columns)
    values = [tuple(row.get(col) for col in columns) for row in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, values)
    conn.commit()
    return len(rows)


def _prepare_matrix_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        flags = item.get("flag_json")
        if isinstance(flags, dict):
            item["flag_json"] = json.dumps(flags, ensure_ascii=False)
        prepared.append(item)
    return prepared


def import_ods(
    *,
    pdf_path: Path,
    report_batch: str = "jinan_20260609",
    output_dir: Path | None = None,
) -> dict[str, Any]:
    parsed = parse_pdf_report(
        pdf_path,
        report_batch=report_batch,
        output_dir=output_dir,
    )

    conn = _get_mysql_connection()
    try:
        ensure_tables(conn)
        n_issue = _upsert(conn, TABLE_ODS_ISSUE, ISSUE_COLUMNS, parsed["issues"])
        n_image = _upsert(conn, TABLE_ODS_IMAGE, IMAGE_COLUMNS, parsed["images"])
        n_rec = _upsert(conn, TABLE_ODS_RECOMMENDATION, REC_COLUMNS, parsed["recommendations"])
        n_matrix = _upsert(
            conn,
            TABLE_ODS_MATRIX,
            MATRIX_COLUMNS,
            _prepare_matrix_rows(parsed["matrix"]),
        )
    finally:
        conn.close()

    for msg in parsed.get("warnings") or []:
        logger.warning(msg)

    return {
        "issue_rows": n_issue,
        "image_rows": n_image,
        "recommendation_rows": n_rec,
        "matrix_rows": n_matrix,
        "warning_count": len(parsed.get("warnings") or []),
        "warnings": parsed.get("warnings") or [],
        "manifest": parsed["manifest"],
        "output_dir": parsed["output_dir"],
    }
