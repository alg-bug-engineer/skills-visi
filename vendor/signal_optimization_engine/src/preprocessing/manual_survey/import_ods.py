"""人工调查 HTML → MySQL ODS 导入。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from preprocessing.manual_survey.parse_html_survey import parse_html_manual_survey
from preprocessing.manual_survey.schema import ALL_DDL, TABLE_ODS_RAW
from preprocessing.timing.timing_csv_to_stage_table import (
    _build_upsert_sql,
    _get_mysql_connection,
)

logger = logging.getLogger(__name__)

ODS_COLUMNS = [
    "record_key",
    "survey_batch",
    "survey_point_id",
    "inter_name_raw",
    "time_period",
    "problem_primary",
    "problem_full_text",
    "problem_desc",
    "lon",
    "lat",
    "coord_srs",
    "display_color",
    "source_file",
]


def ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        for ddl in ALL_DDL:
            cur.execute(ddl)
    conn.commit()


def _upsert(conn, table: str, columns: list[str], rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = _build_upsert_sql(table, columns)
    values = [tuple(row.get(col) for col in columns) for row in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, values)
    conn.commit()
    return len(rows)


def import_ods(
    *,
    html_path: Path,
    survey_batch: str = "jinan_2025",
    output_json: Path | None = None,
) -> dict[str, int | list[str]]:
    rows, warnings = parse_html_manual_survey(html_path, survey_batch=survey_batch)

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    conn = _get_mysql_connection()
    try:
        ensure_tables(conn)
        n_rows = _upsert(conn, TABLE_ODS_RAW, ODS_COLUMNS, rows)
    finally:
        conn.close()

    for msg in warnings:
        logger.warning(msg)

    return {
        "ods_rows": n_rows,
        "warning_count": len(warnings),
        "warnings": warnings,
    }
